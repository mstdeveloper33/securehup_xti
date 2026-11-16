"""Create private directories without changing pre-existing access policies."""

from pathlib import Path


def create_private_directory(path: Path) -> None:
    """Use 0700 for every missing component, independent of permissive umasks.

    Path.mkdir(parents=True) uses the process umask for intermediate directories.
    Existing directories retain their permissions; readiness reports inspect them.
    """
    try:
        path.mkdir(mode=0o700)
    except FileNotFoundError:
        if path.parent == path:
            raise
        create_private_directory(path.parent)
        create_private_directory(path)
    except FileExistsError:
        if not path.is_dir():
            raise
