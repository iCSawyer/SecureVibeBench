#!/usr/bin/env python3
import sys
import docker
from pathlib import Path

def eprint(*args, **kwargs):
    print(*args, file=sys.stderr, **kwargs)

def resolve_image(image: str, image_path_dir: str) -> str:
    eprint(f"[INFO] Requested image: {image}")
    eprint(f"[INFO] Local image directory: {image_path_dir}")

    client = docker.DockerClient(base_url='unix://var/run/docker.sock', timeout=300)


    if ":" in image:
        remote_image = image
        _localid, _mode = image.split(":")[-1].split("-")
    else:
        _localid, _mode = image.split("-")
        remote_image = f"n132/arvo:{_localid}-{_mode}"

    eprint(f"[INFO] Parsed image ID: {_localid}, mode: {_mode}")
    eprint(f"[INFO] Remote fallback tag: {remote_image}")

    image_tar = Path(image_path_dir) / f"{_localid}-{_mode}.tar"
    eprint(f"[INFO] Checking tarball: {image_tar}")

    if image_tar.exists():
        eprint(f"[SUCCESS] Found local tarball: {image_tar}")
        with open(image_tar, "rb") as f:
            loaded_images = client.images.load(f)

        img = loaded_images[0]
        if not img.tags:
            eprint(f"[INFO] Loaded image had no tag, tagging as {remote_image}")
            client.images.get(img.id).tag(remote_image)
            return remote_image
        else:
            eprint(f"[SUCCESS] Loaded image with tag: {img.tags[0]}")
            return img.tags[0]

    eprint(f"[WARN] Local tarball not found. Pulling {remote_image}…")
    last_error = None
    for attempt in range(1, 4):
        try:
            eprint(f"[INFO] Pull attempt {attempt}/3…")
            client.images.pull(remote_image)
            eprint(f"[SUCCESS] Pulled: {remote_image}")
            return remote_image
        except Exception as e:
            eprint(f"[ERROR] Attempt {attempt} failed: {e}")
            last_error = e

    eprint(f"[FATAL] Failed to pull image after 3 attempts: {last_error}")
    sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <image> <image_path_dir>", file=sys.stderr)
        sys.exit(1)
    result = resolve_image(sys.argv[1], sys.argv[2])
    print(result)
