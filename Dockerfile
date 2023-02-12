FROM python:3.7

# Installing ffmpeg is needed for working with timelapses - can be ommitted otherwise
# ZMQ libraries are peerprint dependencies - TODO need to find a way to auto install
# Also install vim for later edit based debugging
RUN apt-get update && apt-get -y install --no-install-recommends ffmpeg libczmq-dev libzmq5 vim && rm -rf /var/lib/apt/lists/*

# IPFS installation for LAN filesharing
RUN wget https://dist.ipfs.tech/kubo/v0.15.0/kubo_v0.15.0_linux-amd64.tar.gz \
  && tar -xvzf kubo_v0.15.0_linux-amd64.tar.gz \
  && cd kubo \
  && bash -c ". ./install.sh" \
  && ipfs --version


RUN adduser oprint
USER oprint

SHELL ["/bin/bash", "-c"]
RUN python -m pip install virtualenv && cd ~ \
  && git clone https://github.com/OctoPrint/OctoPrint && cd OctoPrint \
  && python -m virtualenv venv && source ./venv/bin/activate && python -m pip install -e .[develop,plugins] \
  && echo "source ~/OctoPrint/venv/bin/activate" >> ~/.bashrc \
  && curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.1/install.sh | bash \
  && . ~/.nvm/nvm.sh && nvm install v17 && nvm alias default v17 && nvm use default


ADD . /home/oprint/continuousprint
RUN cd ~/continuousprint && source ~/OctoPrint/venv/bin/activate && octoprint dev plugin:install
CMD octoprint serve
