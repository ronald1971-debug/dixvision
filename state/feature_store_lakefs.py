# ADAPTED FROM: treeverse/lakeFS (Python SDK)
# (lakefs/client.py — Client connection; lakefs/branch.py — Branch.commit(),
#  Branch.diff(), Branch.merge_into(); lakefs/repository.py — Repository,
#  create_branch; lakefs/object.py — StoredObject.upload(), .reader())
"""C-55 — LakeFS feature dataset versioning.

This module adapts the ``lakefs`` Python SDK for Git-like branching over
feature datasets. Branch per experiment, merge after validation.

What survives from upstream (treeverse/lakeFS):
    * **Client** — ``client.py``: connection with endpoint, access key,
      secret key.
    * **Repository** — ``repository.py``: repo operations.
    * **Branch** — ``branch.py``: ``create_branch()``, ``commit()``,
      ``diff()``, ``merge_into()``.
    * **Object** — ``object.py``: ``upload()`` / ``reader()`` for
      parquet/CSV dataset files.

What we replaced:
    * Real ``lakefs`` import is lazy (Protocol seam).
    * In-memory branch/object model for unit tests.
    * Reproducible ML training data via branching.

OFFLINE tier: dataset versioning operations are batch.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class LakeFSCommit:
    """A commit in a LakeFS branch."""

    commit_id: str
    message: str
    branch: str
    timestamp_ns: int = 0


@dataclass(frozen=True, slots=True)
class LakeFSDiff:
    """A diff entry between two refs."""

    path: str
    change_type: str  # "added", "removed", "modified"


class LakeFSFeatureStore:
    """Git-like branching for feature datasets via LakeFS.

    Mirrors ``lakefs.Repository`` + ``Branch`` patterns. In test mode,
    uses in-memory branch/object model.
    """

    def __init__(
        self,
        *,
        endpoint: str = "http://localhost:8000",
        access_key: str = "",
        secret_key: str = "",
        repository: str = "dix-features",
        in_memory: bool = True,
    ) -> None:
        self._endpoint = endpoint
        self._access_key = access_key
        self._secret_key = secret_key
        self._repository = repository
        self._in_memory = in_memory
        # In-memory model
        self._branches: dict[str, list[LakeFSCommit]] = {"main": []}
        self._objects: dict[str, dict[str, bytes]] = {"main": {}}

    def create_branch(self, name: str, source: str = "main") -> bool:
        """Create a new branch from source.

        Mirrors ``Repository.branch(name).create(source_reference=source)``.
        """
        if self._in_memory:
            if name in self._branches:
                return False
            self._branches[name] = list(self._branches.get(source, []))
            self._objects[name] = dict(self._objects.get(source, {}))
            return True
        return self._create_branch_remote(name, source)

    def upload(self, branch: str, path: str, data: bytes) -> bool:
        """Upload an object (dataset file) to a branch.

        Mirrors ``Branch.object(path).upload(data)``.
        """
        if self._in_memory:
            if branch not in self._objects:
                return False
            self._objects[branch][path] = data
            return True
        return self._upload_remote(branch, path, data)

    def commit(self, branch: str, message: str) -> LakeFSCommit | None:
        """Commit staged changes on a branch.

        Mirrors ``Branch.commit(message=...)``.
        """
        if self._in_memory:
            if branch not in self._branches:
                return None
            commit_id = f"c{len(self._branches[branch]) + 1:04d}"
            c = LakeFSCommit(
                commit_id=commit_id,
                message=message,
                branch=branch,
            )
            self._branches[branch].append(c)
            return c
        return self._commit_remote(branch, message)

    def diff(self, branch: str, ref: str = "main") -> list[LakeFSDiff]:
        """Show differences between branch and ref.

        Mirrors ``Branch.diff(other_ref=ref)``.
        """
        if self._in_memory:
            branch_objs = set(self._objects.get(branch, {}).keys())
            ref_objs = set(self._objects.get(ref, {}).keys())
            diffs: list[LakeFSDiff] = []
            for p in branch_objs - ref_objs:
                diffs.append(LakeFSDiff(path=p, change_type="added"))
            for p in ref_objs - branch_objs:
                diffs.append(LakeFSDiff(path=p, change_type="removed"))
            for p in branch_objs & ref_objs:
                if self._objects[branch][p] != self._objects[ref][p]:
                    diffs.append(LakeFSDiff(path=p, change_type="modified"))
            return diffs
        return []

    def merge(self, source_branch: str, into: str = "main") -> bool:
        """Merge source branch into target.

        Mirrors ``Branch.merge_into(destination_branch)``.
        """
        if self._in_memory:
            if source_branch not in self._objects or into not in self._objects:
                return False
            self._objects[into].update(self._objects[source_branch])
            self._branches[into].extend(self._branches.get(source_branch, []))
            return True
        return self._merge_remote(source_branch, into)

    def list_branches(self) -> list[str]:
        """List all branches."""
        if self._in_memory:
            return list(self._branches.keys())
        return []

    def read_object(self, branch: str, path: str) -> bytes | None:
        """Read an object from a branch."""
        if self._in_memory:
            return self._objects.get(branch, {}).get(path)
        return None

    # ---- remote internals ------------------------------------------------

    def _create_branch_remote(self, name: str, source: str) -> bool:
        """Create branch via LakeFS API."""
        try:
            import lakefs

            client = lakefs.Client(
                host=self._endpoint,
                username=self._access_key,
                password=self._secret_key,
            )
            repo = client.repository(self._repository)
            repo.branch(name).create(source_reference=source)
            return True
        except (ImportError, Exception):
            return False

    def _upload_remote(self, branch: str, path: str, data: bytes) -> bool:
        """Upload via LakeFS API."""
        try:
            import lakefs

            client = lakefs.Client(
                host=self._endpoint,
                username=self._access_key,
                password=self._secret_key,
            )
            repo = client.repository(self._repository)
            repo.branch(branch).object(path).upload(data=data)
            return True
        except (ImportError, Exception):
            return False

    def _commit_remote(self, branch: str, message: str) -> LakeFSCommit | None:
        """Commit via LakeFS API."""
        try:
            import lakefs

            client = lakefs.Client(
                host=self._endpoint,
                username=self._access_key,
                password=self._secret_key,
            )
            repo = client.repository(self._repository)
            ref = repo.branch(branch).commit(message=message)
            return LakeFSCommit(
                commit_id=ref.id,
                message=message,
                branch=branch,
            )
        except (ImportError, Exception):
            return None

    def _merge_remote(self, source_branch: str, into: str) -> bool:
        """Merge via LakeFS API."""
        try:
            import lakefs

            client = lakefs.Client(
                host=self._endpoint,
                username=self._access_key,
                password=self._secret_key,
            )
            repo = client.repository(self._repository)
            repo.branch(source_branch).merge_into(repo.branch(into))
            return True
        except (ImportError, Exception):
            return False


__all__ = ["LakeFSCommit", "LakeFSDiff", "LakeFSFeatureStore"]
