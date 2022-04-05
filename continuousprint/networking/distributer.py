from collections import namedtuple
from pulp import pulp, constants as pulp_constants

LPJob = namedtuple("Job", "name materials age")

# TODO determine these via load testing on a raspberry pi
MAX_SCHEDULABLE_JOBS = 10000
MAX_SCHEDULABLE_PRINTERS = 1000

class LPPrinter:
  def __init__(self, name, materials: set, time_until_available, maintenance_score=30, will_pause=False):
    self.name = name
    self.materials = materials
    self.maintenance_score = maintenance_score
    self.will_pause = False
    self.time_until_available = time_until_available
    pass

  def score(self, job):
    if self.will_pause or len(job.materials.difference(self.materials)) > 0:
      return self.maintenance_score + self.time_until_available
    else:
      return self.time_until_available

def assign_jobs_to_printers(jobs, printers):
  assert (len(jobs) < MAX_SCHEDULABLE_JOBS)
  assert (len(printers) < MAX_SCHEDULABLE_PRINTERS)

  max_job_age = max(*[j.age for j in jobs])

  # Score is a combination of the expected added maintenance time from the printer 
  # and the amount of time the job has been sitting in the queue.
  # This ensures that older jobs are printed eventually, but filament changes etc. are
  # avoided.
  printerjobscores = dict([((p.name,j.name), p.score(j) + max_job_age-j.age) for p in printers for j in jobs])

  # Our adjustable variable is which printer is assigned to which jobs, represented here as 
  # a sparse matrix (i.e. dict)
  x = pulp.LpVariable.dicts('JobAssignedToPrinter', printerjobscores.keys(), cat=pulp_constants.LpBinary)

  # Objective: minimize the total score of print jobs assigned
  prob = pulp.LpProblem("Print_Assignment", pulp_constants.LpMinimize)
  prob += pulp.lpSum([printerjobscores[k] * x[k] for k in printerjobscores.keys()])

  # Constraint: We must assign as many jobs as we can
  max_assignable = min(len(jobs), len(printers))
  num_assigned = pulp.lpSum([x[k] for k in printerjobscores.keys()]) 
  prob += (num_assigned == max_assignable)

  # Constraint: Each printer receives at most one job
  for p in printers:
    assignedJobs = pulp.lpSum([x[(p.name,j.name)] for j in jobs])
    prob += (assignedJobs <= 1)

  # Constraint: Each job assigned to at most one printer
  for j in jobs:
    assignedPrinters = pulp.lpSum([x[(p.name, j.name)] for p in printers])
    prob += (assignedPrinters <= 1)

  prob.solve()
  result = {}
  for p in printers:
    for j in jobs:
      if x[(p.name, j.name)].value() == 1:
        result[p.name]=(j.name, printerjobscores[(p.name, j.name)])
  return result


if __name__ == "__main__":
  jobs = [
    LPJob(f"j0", '1', 0),
    LPJob(f"j1", '1', 10),
    LPJob(f"j2", '1', 15),
    LPJob(f"j3", '2', 0),
    LPJob(f"j4", '2', 5),
    LPJob(f"j5", '2', 10),
  ]

  print(jobs)

  printers = [
    LPPrinter("A", "1", 0),
    LPPrinter("B", "1", 0),
    LPPrinter("C", "2", 0),
    LPPrinter("D", "2", 0),
  ]

  assignment = assign_jobs_to_printers(jobs, printers)
  for k,v in assignment.items():
    print(f"Printer {k}: {v}")
