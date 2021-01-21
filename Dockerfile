# set base image (host OS)
FROM --platform=linux/arm/v7 balenalib/raspberry-pi-python

# set the working directory in the container
WORKDIR /controller

# copy the dependencies file to the working directory
COPY requirements.txt .

# copy the config file to the working directory
COPY config.yaml .

# install dependencies
RUN pip install --no-cache-dir -r requirements.txt

# copy the content of the local src directory to the working directory
COPY src/ .

# command to run on container start
CMD [ "python", "./main.py" ]