import hashlib
from typing import Optional
# from storage.queries import addFileWithHash, getPathWithHash, getFiles

class FileShare:
    def __init__(self, filemanager, queries, logger):
        self._fm = filemanager
        self._logger = logger
        self._queries = queries

    def _flatten(self, d: dict) -> set[str]:
      result = set()
      for k, v in d.items():
        if type(v) == dict:
          for p in self._flatten(v):
            result.add(f"{k}/{p}")
        else:
          result.add(k)
      return result

    def analyzeAllNew(self):
        # Analyze any files we haven't already analyzed.
        # Here it's assumed that the list of files can fit reasonably into memory.
        # This may need to be adjusted (and parallelized) if there's a massive number of files to analyze.
        self._logger.info("Comparing file paths in sqlite vs OctoPrint...")
        fm_files = self._flatten(self._fm.list_files())
        self._logger.debug(fm_files)
        db_files = set(self._queries.getFiles().values())
        self._logger.debug(db_files)
        diff = (fm_files - db_files)
        self._logger.info(f"Found {len(diff)} unanalyzed files")
        for path in diff:
          self._logger.info(f"Analyzing {path}")
          self._queries.addFileWithHash(path, self.analyze(path))
    
    def analyze(self, fname) -> str:
        # https://stackoverflow.com/a/3431838
        hash_md5 = hashlib.md5()
        realpath = self._fm.path_on_disk(fname)
        self._logger.info(realpath)
        with open(realpath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        result = hash_md5.hexdigest()
        return result

    def get_filehash_map(self) -> dict:
        return self._queries.getFiles()

    def hash_to_path(self, md5:str) -> Optional[str]:
        return self._queries.getPathWithHash(md5)

