from peerprint.lan_queue import LANPrintQueue
from peerprint.filesharing import Fileshare
import tempfile
import time
import logging
import shutil
import threading
from pathlib import Path

logging.basicConfig(level=logging.DEBUG)

class Runner:
    def __init__(self, args):
        self.td = tempfile.TemporaryDirectory()
        print(f"Copying {args.file} to tempdir {self.td}")
        fname = Path(args.file).name
        shutil.copy2(args.file, self.td.name)

        print(f"Starting fileshare with tempdir {self.td}")
        self.fs = Fileshare("0.0.0.0:0", self.td.name, logging.getLogger("fileshare"))
        self.fs.connect()
        self.manifest = dict(name=args.jobname, count=1, created=int(time.time()), sets=[
            dict(path=fname, count=1)
        ])
        print(f"Posting manifest:", self.manifest)
        self.hash_ = self.fs.post(self.manifest, {fname: str(Path(self.td.name) / fname)})

        print(f"Connecting to '{args.ns}', addr {args.addr}")
        self.t = threading.Thread(target=self.sync_status, daemon=True)
        self.lpq = LANPrintQueue(args.ns, args.addr, None, self.ready, logging.getLogger(args.ns))
        self.started = False
 
    def ready(self):
        if not self.started:
            self.t.start()
            self.started = True

    def sync_status(self):
        sub = False
        while True:
            print("Sync")
            self.lpq.q.syncPeer(dict(name="script", status="SCRIPT", run=None, fs_addr=f"{self.fs.host}:{self.fs.port}"))
            if not sub:
                print(f"Submitting job {self.hash_}")
                self.lpq.q.setJob(self.hash_, self.manifest)
                print(f"Submitted")
                sub = True
            time.sleep(30)


    def cleanup(self):
        self.td.cleanup()


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("ns")
    parser.add_argument("addr", default="0.0.0.0:8769")
    parser.add_argument("jobname")
    parser.add_argument("file")
    args = parser.parse_args()

    r = Runner(args)
    input("Press any key to abort")
    r.cleanup()


if __name__ == "__main__":
    main()
