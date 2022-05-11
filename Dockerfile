FROM docker.io/library/python:3.10-slim

RUN apt-get update && apt-get install -y build-essential

# Configure piwheels repo to use pre-compiled numpy wheels for arm
RUN echo -n "[global]\nextra-index-url=https://www.piwheels.org/simple\n" >> /etc/pip.conf

ADD requirements.txt requirements.txt

RUN pip3 install -r requirements.txt

ADD events events
ADD donkeycar donkeycar
ADD pca9685 pca9685
ADD setup.cfg setup.cfg
ADD setup.py setup.py

ENV PYTHON_EGG_CACHE=/tmp/cache
RUN python3 setup.py install

WORKDIR /tmp
USER 1234

ENTRYPOINT ["/usr/local/bin/rc-pca9685"]
