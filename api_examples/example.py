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


def get_state():
    return requests.get(
        f"{HOST_URL}/plugin/continuousprint/state", headers={"X-Api-Key": UI_API_KEY}
    ).json()


if __name__ == "__main__":
    print(
        "Sending example requests - will stop printer and get its state in two requests"
    )
    set_active(active=False)
    print(get_state())
