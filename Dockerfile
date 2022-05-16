FROM python:3.7

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
