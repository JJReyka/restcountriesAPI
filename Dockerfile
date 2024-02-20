FROM python:3.10
SHELL ["/bin/bash", "-c"]
COPY . /countriesAPI
RUN cd countriesAPI; pip install .
ENV DB_PREFIX='mongo'
CMD hypercorn -b 0.0.0.0 countriesAPI.app