#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import sys
import json
import shutil
import argparse
import subprocess
from pathlib import Path
from zipfile import ZipFile, BadZipFile

MEDIA_EXT = {".mkv", ".mp4"}
SIDECAR_EXT = {".nfo", ".srt", ".ass", ".vtt", ".sub", ".idx", ".jpg", ".jpeg", ".png", ".webp"}

# Liste des extensions sans le point, pour regex
_EXTS_NODOT = "|".join(e[1:] for e in sorted(MEDIA_EXT | SIDECAR_EXT))

"""
Retire toute extension finale (.mkv, .nfo, .png, …) et/ou suffixe '-thumb'
s'ils se trouvent à la fin du bloc technique.
Exemples retirés: '.mkv', '.nfo', '-thumb.png', ' - -thumb.jpg'
"""
def _sanitize_tech(tech: str | None) -> str | None:
    if not tech:
        return None
    t = tech.strip()

    # Enlever éventuellement ' -thumb.<ext>' en fin
    t = re.sub(rf"(?:\s*-\s*)?-thumb\.(?:{_EXTS_NODOT})\s*$", "", t, flags=re.IGNORECASE)
    # Enlever éventuellement '.<ext>' en fin
    t = re.sub(rf"\.(?:{_EXTS_NODOT})\s*$", "", t, flags=re.IGNORECASE)

    # Nettoyage des séparateurs restants
    t = t.strip(" -_.")
    return t or None


# ------------ ZIP & FS helpers ------------
def unzip_pack(root: Path, zip_name: str, dry_run: bool):
    zpath = root / zip_name
    if not zpath.exists():
        print(f"[INFO] Archive absente : {zip_name} (on passe)")
        return
    if dry_run:
        print(f"[DRY] Extraction simulée : {zip_name} -> {root}")
        return
    try:
        with ZipFile(zpath) as zf:
            print(f"[INFO] Extraction : {zip_name}")
            zf.extractall(root)
        print("[OK] Décompression terminée.")
    except BadZipFile:
        print(f"[WARN] Fichier ZIP invalide : {zip_name} — extraction ignorée.")

def ensure_dir(p: Path, dry: bool):
    if dry:
        print(f"[DRY] mkdir -p {p}")
    else:
        p.mkdir(parents=True, exist_ok=True)

def is_saga_dir(p: Path) -> bool:
    return p.is_dir() and p.name.startswith("Saga")

def iter_episode_files(base_dir: Path, extensions: set[str]):
    for root, _, files in os.walk(base_dir):
        for f in files:
            ext = Path(f).suffix.lower()
            if ext in extensions:
                yield Path(root) / f

def unique_dest_path(dest_dir: Path, src: Path) -> Path:
    stem = src.stem
    ext = src.suffix
    candidate = dest_dir / (stem + ext)
    if not candidate.exists():
        return candidate
    i = 1
    while True:
        candidate = dest_dir / (f"{stem} ({i}){ext}")
        if not candidate.exists():
            return candidate
        i += 1


def same_fs(a: Path, b: Path) -> bool:
    try:
        return a.stat().st_dev == b.stat().st_dev
    except FileNotFoundError:
        return a.stat().st_dev == b.parent.stat().st_dev

def do_hardlink(src: Path, dst: Path, dry_run: bool) -> bool:
    if dry_run:
        print(f"[DRY] LINK: '{src}' -> '{dst}'")
        return True
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        os.link(src, dst)
        print(f"[OK] LINK: {src} -> {dst}")
        return True
    except OSError as e:
        print(f"[ERR] Hardlink échoué: {src} -> {dst} : {e}")
        return False

def do_reflink(src: Path, dst: Path, dry_run: bool) -> bool:
    if dry_run:
        print(f"[DRY] REFLINK: '{src}' -> '{dst}'")
        return True
    dst.parent.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(["cp", "--reflink=always", "--preserve=all", str(src), str(dst)],
                       check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        print(f"[OK] REFLINK: {src} -> {dst}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"[WARN] Reflink impossible, fallback COPY: {e.stderr.decode(errors='ignore').strip()}")
        try:
            shutil.copy2(str(src), str(dst))
            print(f"[OK] COPY: {src} -> {dst}")
            return True
        except Exception as ee:
            print(f"[ERR] COPY échouée après reflink: {ee}")
            return False

def move_or_copy(src: Path, dst: Path, mode: str, dry_run: bool):
    if mode == "link":
        return do_hardlink(src, dst, dry_run)
    if mode == "reflink":
        return do_reflink(src, dst, dry_run)

    if dry_run:
        action = "MOVE" if mode == "move" else "COPY"
        print(f"[DRY] {action}: '{src}' -> '{dst}'")
        return True
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if mode == "move":
            shutil.move(str(src), str(dst))
            print(f"[OK] MOVE: {src} -> {dst}")
        else:
            shutil.copy2(str(src), str(dst))
            print(f"[OK] COPY: {src} -> {dst}")
        return True
    except Exception as e:
        print(f"[ERR] {mode.upper()} échoué: {src} -> {dst} : {e}")
        return False

# ------------ Parsing / renaming helpers ------------
re_sxe = re.compile(r"(?:^|[\s_-])S(?P<s>\d{2})E(?P<e>\d{3})(?:\D|$)", re.IGNORECASE)
re_leading_3 = re.compile(r"(?:^|[\s_-])(?P<e>\d{3})(?:\D|$)")
re_title_after_sxe = re.compile(r"S\d{2}E\d{3}\s*-\s*(?P<title>[^-]+)")
re_title_after_num = re.compile(r"(?<!\d)(\d{3})\s*-\s*(?P<title>[^-]+)")

def parse_episode_number(name: str):
    m = re_sxe.search(name)
    if m:
        return int(m.group("e")), int(m.group("s"))
    m = re_leading_3.search(name)
    if m:
        return int(m.group("e")), None
    return None, None

def try_extract_title(name: str):
    m = re_title_after_sxe.search(name)
    if m:
        return m.group("title").strip()
    m = re_title_after_num.search(name)
    if m:
        return m.group("title").strip()
    return None

def split_tech_block(name: str):
    """
    Sépare au premier ' - ' après l'ID pour conserver le bloc technique,
    puis nettoie le 'tech' de toute extension / suffixe '-thumb' final.
    """
    title = try_extract_title(name)
    if not title:
        return None, None
    idx = name.find(title)
    if idx == -1:
        return title, None
    after = name[idx + len(title):].lstrip(" -")
    tech = after.strip(" -") if after else None
    tech = _sanitize_tech(tech)
    return title, tech


def build_new_basename(show_name: str, season: int, ep: int, title: str | None, tech: str | None):
    base = f"{show_name} - S{season:02d}E{ep:03d}"
    if title:
        base += f" - {title.strip()}"
    if tech:
        base += f" - {tech.strip()}"
    return base

def make_stem_key(p: Path):
    stem = p.stem
    stem = re.sub(r"-thumb$", "", stem, flags=re.IGNORECASE)
    stem_n = re.sub(r"\s+", " ", stem).strip()
    return (stem_n.lower(), p.parent.as_posix())

# ------------ Config ------------
def load_config(cfg_path: Path):
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    ep_to_season = {}
    season_to_folder = {}
    for s in cfg["seasons"]:
        season_to_folder[s["season"]] = s["folder"]
        start, end = s["range"]
        for ep in range(int(start), int(end) + 1):
            ep_to_season[ep] = s["season"]
    return cfg["show_name"], ep_to_season, season_to_folder

# ------------ Pipeline ------------
def main():
    ap = argparse.ArgumentParser(
        description="Dézippe, rassemble, renomme et range One Piece Kaï pour Plex."
    )
    ap.add_argument("--zip-name", default="One Piece Kaï (Pack Plex).zip",
                    help="Nom de l'archive à extraire si présente (défaut: %(default)s)")
    ap.add_argument("--episodes-dir", default="One Piece Kaï - Episodes",
                    help="Dossier central où regrouper les épisodes (défaut: %(default)s)")
    ap.add_argument("--show-root", default="One Piece Kaï",
                    help="Dossier contenant 'Saison 1', 'Saison 2', ... et les assets (défaut: %(default)s)")
    ap.add_argument("--config", default="seasons_config.json",
                    help="Fichier de config JSON (lu depuis le CWD si relatif) (défaut: %(default)s)")
    ap.add_argument("--ext", default=".mkv,.mp4",
                    help="Extensions vidéo à collecter (défaut: %(default)s)")
    ap.add_argument("--mode", choices=["move", "copy", "link", "reflink"], default="move",
                    help="Action lors du rassemblement ET du rangement (défaut: move)")
    ap.add_argument("--dry-run", action="store_true", help="Simuler sans rien modifier")
    args = ap.parse_args()

    root = Path.cwd()
    episodes_dir = (root / args.episodes_dir).resolve()
    show_root = (root / args.show_root).resolve()

    cfg_path = Path(args.config)
    if not cfg_path.is_absolute():
        cfg_path = root / cfg_path

    extensions = {e.strip().lower() if e.strip().startswith(".") else "." + e.strip().lower()
                  for e in args.ext.split(",") if e.strip()}

    print(f"[CTX] CWD: {root}")
    print(f"[CFG] mode={args.mode} | dry={args.dry_run} | zip='{args.zip-name if hasattr(args,'zip-name') else args.zip_name}'")
    print(f"[CFG] episodes_dir='{episodes_dir}' | show_root='{show_root}' | config='{cfg_path}' | ext={sorted(extensions)}")

    # 1) Dézipper
    unzip_pack(root, args.zip_name, args.dry_run)

    # 2) Créer le dossier central des épisodes
    ensure_dir(episodes_dir, args.dry_run)

    # 3) Rassembler depuis tous les 'Saga*' vers le dossier central
    saga_dirs = [d for d in root.iterdir() if is_saga_dir(d)]
    saga_dirs.sort(key=lambda p: p.name)
    if not saga_dirs:
        print("[WARN] Aucun dossier 'Saga*' trouvé à la racine. (Peut-être déjà rassemblé ?)")
    else:
        print(f"[INFO] Dossiers Saga détectés ({len(saga_dirs)}):")
        for d in saga_dirs:
            print(f"       - {d.name}")

        collected, failed = 0, 0
        for saga in saga_dirs:
            for ep in iter_episode_files(saga, extensions):
                target = unique_dest_path(episodes_dir, ep)
                mode = args.mode
                if mode == "link" and not same_fs(ep, episodes_dir):
                    print(f"[INFO] Hardlink impossible (FS différent) -> fallback COPY pour '{ep.name}'")
                    mode = "copy"
                ok = move_or_copy(ep, target, mode, args.dry_run)
                collected += 1 if ok else 0
                failed += 0 if ok else 1
        print(f"[RES] Rassemblement: OK={collected} | Échecs={failed}")

    # 4) Charger la config
    if not cfg_path.exists():
        print(f"[ERR] Config JSON introuvable: {cfg_path}")
        sys.exit(2)
    if not show_root.exists():
        print(f"[INFO] Création du show_root: {show_root}")
        ensure_dir(show_root, args.dry_run)

    show_name, ep_to_season, season_to_folder = load_config(cfg_path)
    print(f"[CFG] show='{show_name}', saisons={len(season_to_folder)}")

    # 5) Renommer + ranger depuis le dossier central
    all_files = [p for p in episodes_dir.rglob("*") if p.is_file()]
    # index souple par stem
    all_files_by_stem = {}
    for p in all_files:
        key = make_stem_key(p)
        all_files_by_stem.setdefault(key, []).append(p)

    processed = 0
    skipped = 0

    videos = [p for p in all_files if p.suffix.lower() in MEDIA_EXT]
    videos.sort()
    for vid in videos:
        ep, season_hint = parse_episode_number(vid.name)
        if not ep:
            print(f"[WARN] Numéro d'épisode introuvable dans: {vid.name}")
            skipped += 1
            continue
        season = season_hint if season_hint else ep_to_season.get(ep)
        if not season:
            print(f"[WARN] Épisode {ep:03d} hors plages config: {vid.name}")
            skipped += 1
            continue

        title, tech = split_tech_block(vid.name)
        base_new = build_new_basename(show_name, season, ep, title, tech)

        season_folder_name = season_to_folder.get(season, f"Saison {season}")
        dest_dir = show_root / season_folder_name
        ensure_dir(dest_dir, args.dry_run)

        key = make_stem_key(vid)
        group_files = all_files_by_stem.get(key, [vid])

        for f in group_files:
            ext = f.suffix.lower()
            if ext in MEDIA_EXT:
                new_name = base_new + ext
                # après: new_name = base_new + ext
                if new_name.lower().endswith(ext.lower() * 2):  # cas pathologique type '.mkv.mkv'
                    new_name = new_name[:-len(ext)]
            else:
                suffix = "-thumb" if f.stem.endswith("-thumb") else ""
                new_name = base_new + suffix + ext
            target = dest_dir / new_name

            mode = args.mode
            if mode == "link" and not same_fs(f, dest_dir):
                print(f"[INFO] Hardlink impossible (FS différent) -> fallback COPY pour '{f.name}'")
                mode = "copy"

            ok = move_or_copy(f, target, mode, args.dry_run)
            processed += 1 if ok else 0
            skipped += 0 if ok else 1

    # 6) Normaliser les fichiers restants dans chaque Saison (001 -> SxxEyyy)
    print("\n[INFO] Normalisation des fichiers annexes dans les dossiers Saison...")
    for season, folder in season_to_folder.items():
        sdir = show_root / folder
        if not sdir.exists():
            continue
        for f in sdir.iterdir():
            if not f.is_file():
                continue
            if re_sxe.search(f.name):
                continue
            ep, _ = parse_episode_number(f.name)
            if not ep:
                continue
            s = ep_to_season.get(ep, season)
            title, tech = split_tech_block(f.name)
            base_new = build_new_basename(show_name, s, ep, title, tech)
            ext = f.suffix
            suffix = "-thumb" if f.stem.endswith("-thumb") else ""
            new_name = base_new + suffix + ext
            target = f.parent / new_name
            if target.exists():
                continue
            ok = move_or_copy(f, target, "move", args.dry_run)
            if ok:
                print(f"[FIX] Renommé {f.name} -> {new_name}")

    print(f"\n[RES] Rangements: Traités={processed} | Skippés={skipped}")
    print(f"[TIP] Vérifie: {show_root}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[INFO] Interrompu par l'utilisateur.")
        sys.exit(1)
