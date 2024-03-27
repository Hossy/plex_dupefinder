# Dockerizing the Plex Dupefinder Python Application

This guide outlines the steps for Dockerizing the Plex Dupefinder Python application using Docker.

## Folder Structure

Ensure that your project has the following folder structure:

```
plex_dupefinder/
│
└── app/
    └── Dockerfile  # (Included from git checkout)
    └── ... (all contents from the git checkout)
```

- `plex_dupefinder/`: Root directory for the Plex Dupefinder project.
- `app/`: Contains all files and directories retrieved from the git checkout, including the Dockerfile.

## Setting Up the Folder Structure

Follow these steps to set up the folder structure and retrieve your Python application files:

1. Open a terminal and navigate to the desired directory for your project.
2. Run the following command to clone your repository and create the `app/` folder:
   ```
   git clone https://github.com/hellblazer315/plex_dupefinder.git app
   ```

This command clones your repository and creates the `/app` folder containing all files and directories from the git checkout, including the Dockerfile.

## Building the Docker Image

Follow these steps to build the Docker image for your Python application:

1. Open a terminal and navigate to the root directory of your project.
2. Run the following command to build the Docker image:
   ```
   APP_PATH='plex_dupefinder/app'
   docker build -t plex_dupefinder $APP_PATH
   ```

   - Replace `plex_dupefinder/app` in the APP_PATH variable with the absolute path to the `app/` directory on your system.

This command builds the Docker image named `plex_dupefinder` using the Dockerfile located in the `app/` directory.

### Preserving the Locally-Built Image

To preserve the locally-built image when running `docker system prune`, follow these additional steps:

1. When building the Docker image, add a label to it using the `--label` flag:
   ```
   APP_PATH='plex_dupefinder/app'
   docker build -t plex_dupefinder --label "preserve=true" app
   ```

   - Replace `plex_dupefinder/app` in the APP_PATH variable with the absolute path to the `app/` directory on your system.

   This command adds the label `preserve=true` to the `plex_dupefinder` image.
   

2. When running `docker system prune`, use the `--filter` flag to exclude images with the `preserve=true` label:
   ```
   docker system prune -af --filter "label!=preserve=true"
   ```

   This command prunes all unused data (containers, networks, volumes, and images) except those with the `preserve=true` label, ensuring that the locally-built image is preserved from deletion.

## Running the Docker Container

Once the Docker image is built, you can run it as a Docker container using the following steps:

1. Run the following command to start a Docker container from the image:
   ```
   APP_PATH='plex_dupefinder/app'
   docker run --rm --name plex_dupefinder --env-file $APP_PATH/docker.env -v $APP_PATH:/app plex_dupefinder
   ```

   - Replace `plex_dupefinder/app` in the APP_PATH variable with the absolute path to the `app/` directory on your system.

2. If running with `SKIP_OTHER_DUPES=false`, add the `-i` option to the `docker run` command:
   ```
   APP_PATH='plex_dupefinder/app'
   docker run -i --rm --name plex_dupefinder --env-file $APP_PATH/docker.env -v $APP_PATH:/app plex_dupefinder
   ```

   The `-i` option ensures interactive mode, allowing input to be sent to the container.
