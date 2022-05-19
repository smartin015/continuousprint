from .database import JobView, SetView


class LANJobView(JobView):
    def __init__(self, manifest, hash_, lq):
        self.lq = lq
        for attr in ("name", "count", "remaining", "created"):
            setattr(self, attr, manifest[attr])
        self.id = hash_
        self.sets = []
        self.draft = False
        self.acquired = None
        self.sets = [LANSetView(s, self, i, lq) for i, s in enumerate(manifest["sets"])]

    def save(self):
        print("LANJobView.save of ", str(self.as_dict()))
        self.lq.setJob(self.id, self.as_dict())


class LANSetView(SetView):
    def __init__(self, data, job, rank, lq):
        self.job = job
        self.sd = False
        self.rank = rank
        self.id = f"{job.id}_{rank}"
        for attr in ("path", "count", "remaining"):
            setattr(self, attr, data[attr])
        self.material_keys = ",".join(data.get("materials", []))
        self.profile_keys = ",".join(data.get("profiles", []))

    def save(self):
        self.job.save()
