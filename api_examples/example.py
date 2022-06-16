import requests

# See https://docs.octoprint.org/en/master/api/general.html#authorization for
# where to get this value
UI_API_KEY = "CHANGEME"

# Change this to match your printer
HOST_URL = "http://localhost:5000"


def set_active(active=True):
    return requests.post(
        f"{HOST_URL}/plugin/continuousprint/set_active",
        headers={"X-Api-Key": UI_API_KEY},
        data={"active": active},
    ).json()


def add_set(path, sd=False, count=1, jobName="Job", jobDraft=True):
    return requests.post(
        f"{HOST_URL}/plugin/continuousprint/set/add",
        headers={"X-Api-Key": UI_API_KEY},
        data=dict(
            path=path,
            sd=sd,
            count=count,
            jobName=jobName,
            jobDraft=jobDraft,
        ),
    ).json()


def get_state():
    return requests.get(
        f"{HOST_URL}/plugin/continuousprint/state/get",
        headers={"X-Api-Key": UI_API_KEY},
    ).json()


if __name__ == "__main__":
    print("Sending example requests to", HOST_URL)
    print("Stopping management")
    set_active(active=False)
    print("Adding an example set/job")
    add_set("example.gcode")
    print("Fetching queue state")
    print(get_state())
