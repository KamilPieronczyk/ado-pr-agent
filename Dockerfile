FROM mcr.microsoft.com/azure-cli:2.79.0

WORKDIR /app

RUN tdnf install -y git bash python3-pip && \
    az extension add --name azure-devops

COPY pyproject.toml ruff.toml mypy.ini README.md ./
COPY src ./src

RUN python3 -m pip install --root-user-action=ignore .

ENTRYPOINT ["ado-ai-pr-review"]
