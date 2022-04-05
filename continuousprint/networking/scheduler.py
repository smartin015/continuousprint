import numpy as np
from functools import cache
from collections import defaultdict
from dataclasses import dataclass

@dataclass
class Job:
  start_material: str
  end_material: str
  changes: int
  duration: int
  age_rank: int # The number of time this job has been "cut in line"

@dataclass
class Period:
  start: int
  end: int
  avail: int

class JobSchedulerDP:

  def __init__(self, schedule: list[Period], jobs: list[Job], start_material: str, logger):
    self._logger = logger
    self.schedule = schedule
    self.jobs = jobs

    for i,s in enumerate(self.schedule):
      assert s.start >= 0, f"Schedule item {i} has start value less than 0: {s.start}"
      assert s.end >= 0, f"Schedule item {i} has end value less than 0: {s.end}"
      assert s.end >= 0, f"Schedule item {i} has negative availability: {s.avail}"
 
    # Collect distinct material IDs
    self.materials = set([start_material])
    for j in jobs:
      self.materials.add(j.start_material)
      self.materials.add(j.end_material)
    # Convert material strings to integers for speediness
    self.idx_to_material = list(self.materials)
    self.material_to_idx = dict([(m,i) for i, m in enumerate(self.idx_to_material)])

    # Integer-ify all materials in data    
    self.start_material = self.material_to_idx[start_material]
    for j in self.jobs:
      j.start_material = self.material_to_idx[j.start_material]
      j.end_material = self.material_to_idx[j.end_material]

    total_duration = sum([j.duration for j in self.jobs])
    assert total_duration <= schedule[-1].end, f"Job duration {total_duration} exceeds schedule duration {schedule[-1].end}"
 
  @cache
  def ordered_candidates(self, exclude: frozenset, next_material: str, age_rank: int):
    # This returns candidate jobs in an order which minimizes the added cost of switching from the job to a future state.
    scored = []
    for j in range(len(self.jobs)):
      if j in exclude:
        continue
      job = self.jobs[j]
      score = job.changes # Each material change incurs a cost for the job
      if job.end_material != next_material: # Material switches cost manual effort
        score = 1
      if job.age_rank < age_rank: # Try to schedule older jobs first
        score += 1
      scored.append((j, score))
    scored.sort(key=lambda s: s[1])
    return tuple(scored)

  @cache
  def schedule_at(self, t): # Simple binary search for the proper schedule position
    imax = len(self.schedule) - 1
    imin = 0
    j = 0
    while imax >= imin and j < len(self.schedule):
      s = self.schedule[j]
      if s.start <= t and s.end >= t:
        return s, j # We're within the boundary of this schedule block
      elif s.start > t:
        imax = i-1 # We're earlier in the schedule
      elif s.end < t:
        imin = i+1 # We're later in the schedule
      j += 1

    raise Exception(f"schedule_at({t}) failed: imax {imax} imin {imin}, schedule {self.schedule}")


  def debug(self, order, pd=600):
    i = 0
    jstart = 0
    prev_s = None
    prev_m = self.start_material
    annotated = False
    for t in range(0, self.schedule[-1].end, pd):
      j = self.jobs[order[i]]
      while jstart+j.duration < t:
        jstart += j.duration
        i += 1
        if i >= len(order): # schedule may be longer than total job duration
          return
        j = self.jobs[order[i]]
        annotated=False
      s, si = self.schedule_at(t)
      if prev_s is None or prev_s != s:
        self._logger.debug(f"Schedule block {si:02}: {s.start:4} - {s.end:4}, availability {s.avail}")
        prev_s = s

      appendix = ""
      if prev_m is None or j.end_material != prev_m:
        appendix = "CHANGE"
      if not annotated:
        appendix += f" +{j.changes}"
        annotated=True
      prev_m = j.start_material
      self._logger.debug(f"@t={t:4}: j{order[i]:02} ({j.start_material} - {j.end_material}) {appendix}")

  def run(self):
    best = None
    end_sec = sum([job.duration for job in self.jobs])
    self._logger.info(f"Running scheduler on {len(self.jobs)} job(s), total time {end_sec}s")
    for j in range(len(self.jobs)):
      result = self.estimate(len(self.jobs)-1, 0, end_sec, frozenset())
      if result is None:
        continue
      (score, seq) = result
      if best is None or score < best[0]:
        best = (score, seq)
    return best

  # TODO turn job_idx into job_id to obviate cachebusting when trying to schedule different additional jobs
  @cache # Note: cur_time always the same for a given jobs_used, but it's less work to cache it than re-calculate
  def estimate(self, job_idx: int, effort_within_sched: int, cur_time: int, jobs_used:frozenset):
    # print(f"est job{job_idx} effort {effort_within_sched} t={cur_time}, used={jobs_used}")
    cs, _ = self.schedule_at(cur_time)
    if effort_within_sched > cs.avail:
      # print("invalid")
      return None # Invalid condition; no solution
  
    # Compute current & previous time
    jobs_used |= set([job_idx])
    prev_time = cur_time - self.jobs[job_idx].duration
    ps, _ = self.schedule_at(prev_time)
    if ps.end < cur_time: # We crossed schedule boundaries
      effort_within_sched = 0

    if len(jobs_used) == len(self.jobs):
      if self.jobs[job_idx].start_material != self.start_material:
        effort_within_sched += 1
      if effort_within_sched > ps.avail:
        # print("invalid last")
        return None
      # print("valid")
      return (effort_within_sched, tuple([job_idx])) # All jobs used; nothing to do. This is the same as cur_time <= 0.

    for j, cost in self.ordered_candidates(jobs_used, self.jobs[job_idx].start_material, self.jobs[job_idx].age_rank):
      result = self.estimate(j, effort_within_sched+cost, prev_time, jobs_used)
      if result is None:
        continue
    
      # Jobs are ordered by best-ness, so return the first one that is valid
      return (result[0], result[1]+tuple([job_idx]))

    # No valid solutions, return none
    return None

if __name__ == "__main__":
  import yaml
  import sys
  import time
  import logging
  logging.basicConfig(level=logging.DEBUG)
  if len(sys.argv) != 2:
    sys.stderr.write(f"Usage: {sys.argv[0]} [testdata/order.yaml]\n")
    sys.exit(1)

  with open(sys.argv[1], "r") as f:
    data = yaml.safe_load(f.read())
  
  s = JobSchedulerDP([Period(**s) for s in data['schedule']], [Job(**j) for j in data['jobs']], data['start_material'], logging.getLogger())

  start = time.perf_counter()
  result = s.run()
  end = time.perf_counter()
  print(f"Took {int((end-start)*1000000)}us")
  print("Result", result)
  if result is not None:
    s.debug(result[1])
