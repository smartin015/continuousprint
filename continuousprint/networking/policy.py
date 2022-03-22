from print_queue import QueueItem


class Policy(Enum):
    # Iterate sequentially through prints, picking the first print that hasn't
    # yet been started
    SEQUENTIAL = 1

    # Try to clear the bed as few times as possible (reduce number of chances for
    # initial print failure, e.g. due to bed adhesion)
    LEAST_CLEARING = 2

    # Try to clear the bed as many times as possible (maximize the rate of
    # completed prints)    
    MOST_CLEARING = 3


SchedulePeriod = namedtuple('SchedulePeriod', ['duration', 'policy', 'manual_eta'])

class Schedule:
    def __init__(self, periods: list(SchedulePeriod)):
      self.periods = periods

    def at(self, t: int)
      # TODO better than linear
      elapsed = 0
      for p in periods:
        if t > elapsed:
          return p
        elapsed += p.duration
      return None



def material_str(item):
    return ":".join(i.material)

def estimate_runtime(item: QueueItem):
    return 0 # TODO        

# Schedule is a list of (policy, duration_seconds, blocking_cost_sec). It MUST provide a schedule
# for at least as long as min_schedule_length_sec
def order_by_policy(schedule: Schedule, current: QueueItem, future: QueueItem[], min_schedule_length_sec=60*60*24):
  future = [f for f in enumerate(future) if f[1].end_ts is None] # Scale down to 

  # Generate info needed to make a good choice
  material_counts = defaultdict(0)
  material_times = defaultdict(0)
  runtimes = {}
  for i, item in future:
    material_counts[material_str(item)] += 1
    runtime = estimate_runtime(item)
    runtimes[i] = runtime
    material_times[material_str(item)] += runtime

  t = 0
  result = []
  seen = set()
  for _ in range(len(future)):
    
    if t > min_schedule_length_sec:
      break
    elif t > next_sched:
      sched_idx += 1
      next_sched += schedule[sched_idx][1]

    pick = None
    p, _, block_sec = schedule[sched_idx][0]
    if p == Policy.SEQUENTIAL:
      # Pick the next one we haven't seen yet
      for (i, _) in future:
        if i not in seen:
          pick = i
          break
    elif p == Policy.LEAST_CLEARING:
      # Pick the item that runs for the longest 
      

    result.append(pick)
    seen.add(pick)
    t += runtimes[pick]
