import hashlib
from typing import Optional
from functools import cache
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
        self._logger.debug("Comparing file paths in sqlite vs OctoPrint...")
        fm_files = self._flatten(self._fm.list_files())
        db_files = set(self._queries.getFiles('local').values())
        diff = (fm_files - db_files)
        self._logger.debug(f"Found {len(diff)} unanalyzed files")
        results = {}
        for path in diff:
          self._logger.debug(f"Analyzing {path}")
          results[self.analyze(path)] = path
        self._queries.syncFiles('', 'local', results, remove=False)
    
    def analyze(self, fname) -> str:
        # https://stackoverflow.com/a/3431838
        hash_md5 = hashlib.md5()
        realpath = self._fm.path_on_disk(fname)
        self._logger.debug(f"Analyzing {realpath}")
        with open(realpath, "rb") as f:
            for chunk in iter(lambda: f.read(4096), b""):
                hash_md5.update(chunk)
        result = hash_md5.hexdigest()
        return result

    def downloadFile(self, url:str, path:str):
        # Get the equivalent path on disk
        dest = self._fm.path_on_disk(path)
        written = 0
        self._logger.debug(f"Opening URL {url}")
        # Consider using octoprint.storage.LocalFileStorage.add_file()
        # https://docs.octoprint.org/en/master/modules/filemanager.html#octoprint.filemanager.storage.LocalFileStorage.add_file        
        with requests.get(url, stream=True) as r:
          r.raise_for_status()
          with open(dest, 'wb') as f:
              for chunk in r.iter_content(chunk_size=8192):
                  f.write(chunk)
                  written += len(chunk)
        self._logger.debug(f"Wrote {written}B to {path}")

    @cache
    def estimateDuration(self, path):
        if self._fm.has_analysis(path):
            return self._fm.get_additional_metadata(path).get('estimatedPrintTime')
        else:
            raise Exception("TODO run metadata analysis")

