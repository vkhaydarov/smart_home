# set base image (host OS)
#FROM --platform=linux/arm/v7 balenalib/raspberry-pi-python
FROM python

# set the working directory in the container
WORKDIR /controller

# copy files
COPY src ./src
COPY requirements.txt .
COPY config.yaml .
COPY main.py .

# install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# command to run on container start
CMD [ "python", "main.py" ]
