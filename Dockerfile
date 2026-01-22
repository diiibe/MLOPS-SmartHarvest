# Use official Python runtime as a parent image
FROM python:3.9-slim

# Set environment variables
# PYTHONDONTWRITEBYTECODE: Prevents Python from writing pyc files to disc
# PYTHONUNBUFFERED: Prevents Python from buffering stdout and stderr
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies (if any are needed for scipy/pandas/folium)
# RUN apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the current directory contents into the container at /app
COPY . .

# Create a user to avoid running as root (Best Practice)
RUN useradd -m appuser && chown -R appuser /app
USER appuser

# Define the command to run your application
# For now, we run the offline runner to demonstrate the app works "out of the box"
CMD ["python", "tests/ci_offline_runner.py"]
