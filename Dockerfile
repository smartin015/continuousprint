FROM python:3.10

SHELL ["/bin/bash", "-c"]
RUN python3 -m pip install virtualenv && git clone https://github.com/OctoPrint/OctoPrint && cd OctoPrint && virtualenv venv && pip install -e .[develop,plugins]
ADD . /continuousprint
RUN cd continuousprint && source /OctoPrint/venv/bin/activate && octoprint dev plugin:install

RUN adduser oprint
USER oprint
CMD source /OctoPrint/venv/bin/activate && octoprint serve
