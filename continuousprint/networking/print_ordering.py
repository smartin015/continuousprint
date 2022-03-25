import numpy as np
from functools import cache
from collections import defaultdict
from dataclasses import dataclass

@dataclass
class Job:
  material: str
  changes: int
  duration: int
  age_rank: int # The number of time this job has been "cut in line"

@dataclass
class Sched:
  start: int
  end: int
  avail: int

class JobSchedulerDP:

  def __init__(self, schedule, jobs, start_material):
    # Each job has material set and time-to-print
    # Each schedule item has an end time and a max expected manual interventions
    self.schedule = schedule
    self.jobs = jobs
    self.start_material = start_material
 
    total_duration = sum([j.duration for j in self.jobs])
    assert total_duration <= schedule[-1].end, f"Job duration {total_duration} exceeds schedule duration {schedule[-1].end}"
 
  @cache
  def ordered_candidates(self, exclude: frozenset, material: str, age_rank: int):
    # This returns candidate jobs in an order which minimizes the added cost of switching from the job to a future state.
    scored = []
    for j in range(len(self.jobs)):
      if j in exclude:
        continue
      job = self.jobs[j]
      score = job.changes # Each material change incurs a cost for the job
      if job.material != material: # Material switches cost manual effort
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
      i = int((imax - imin)/2) + imin
      s = self.schedule[i]
      if s.start <= t and s.end >= t:
        return s, i # We're within the boundary of this schedule block
      elif s.start > t:
        imax = i-1 # We're earlier in the schedule
      elif s.end < t:
        imin = i+1 # We're later in the schedule
      j += 1

    raise Exception(f"schedule_at({t}) failed: imax {imax} imin {imin}")

  def debug(self, order, pd=10):
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
        j = self.jobs[order[i]]
        annotated=False
      s, si = self.schedule_at(t)
      if prev_s is None or prev_s != s:
        print(f"Schedule block {si:02}: {s.start:4} - {s.end:4}, availability {s.avail}")
        prev_s = s

      appendix = ""
      if prev_m is None or j.material != prev_m:
        prev_m = j.material
        appendix = "CHANGE"
      if not annotated:
        appendix += f" +{j.changes}"
        annotated=True
      print(f"@t={t:4}: j{order[i]:02} ({j.material}) {appendix}")

  def run(self):
    best = None
    for j in range(len(self.jobs)):
      result = self.estimate(len(self.jobs)-1, 0, self.schedule[-1].end, frozenset())
      if result is None:
        continue
      (score, seq) = result
      if best is None or score < best[0]:
        best = (score, seq)
    return best

  # TODO turn job_idx into job_id to obviate cachebusting when trying to schedule different additional jobs
  @cache # Note: cur_time always the same for a given jobs_used, but it's less work to cache it than re-calculate
  def estimate(self, job_idx, effort_within_sched, cur_time, jobs_used:frozenset):
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
      if self.jobs[job_idx].material != self.start_material:
        effort_within_sched += 1
      if effort_within_sched > ps.avail:
        # print("invalid last")
        return None
      # print("valid")
      return (effort_within_sched, tuple([job_idx])) # All jobs used; nothing to do. This is the same as cur_time <= 0.

    for j, cost in self.ordered_candidates(jobs_used, self.jobs[job_idx].material, self.jobs[job_idx].age_rank):
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

  if len(sys.argv) != 2:
    sys.stderr.write(f"Usage: {sys.argv[0]} [testdata/order.yaml]\n")
    sys.exit(1)

  with open(sys.argv[1], "r") as f:
    data = yaml.safe_load(f.read())
  
  s = JobSchedulerDP([Sched(**s) for s in data['schedule']], [Job(**j) for j in data['jobs']], data['start_material'])

  start = time.perf_counter()
  result = s.run()
  end = time.perf_counter()
  print(f"Took {int((end-start)*1000000)}us")
  print("Result", result)
  if result is not None:
    s.debug(result[1])
