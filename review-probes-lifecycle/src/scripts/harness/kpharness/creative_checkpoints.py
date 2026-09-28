"""Constrain the inherited checkpoint copy/delete operations to private roots."""
from pathlib import Path

from .checkpoints import Checkpoints, CheckpointError


def child(root: Path, name: str) -> Path:
    if not name or name in ('.', '..') or '/' in name or '\\' in name:
        raise CheckpointError(f'bad checkpoint/save name {name!r}')
    path = root / name
    if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
        raise CheckpointError(f'checkpoint/save destination escapes root: {path}')
    return path


class CreativeCheckpoints(Checkpoints):
    def __init__(self, target, save_dir, root):
        self._root_identity = Path(root).resolve()
        self._save_identity = Path(save_dir).resolve()
        super().__init__(target, save_dir, root)

    def path(self, name):
        if self.root.resolve() != self._root_identity:
            raise CheckpointError('checkpoint root identity changed')
        return child(self.root, name)

    def _save_path(self, folder):
        if self.save_dir.resolve() != self._save_identity:
            raise CheckpointError('save root identity changed')
        return child(self.save_dir, folder)

    def store(self, name, folder, extra=None):
        self.path(name)
        src = self._save_path(folder)
        if any(p.is_symlink() for p in src.rglob('*')):
            raise CheckpointError('save contains symlinks')
        return super().store(name, folder, extra)

    def restore(self, name):
        folder = str(self.meta(name)['folder'])
        self._save_path(folder)
        src = child(self.path(name), folder)
        if any(p.is_symlink() for p in src.rglob('*')):
            raise CheckpointError('checkpoint contains symlinks')
        return super().restore(name)
