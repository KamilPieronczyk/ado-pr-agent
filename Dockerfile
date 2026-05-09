FROM mcr.microsoft.com/azure-cli:2.79.0

WORKDIR /app

RUN apk add --no-cache git bash && \
    az extension add --name azure-devops

COPY pyproject.toml ruff.toml mypy.ini ./
COPY src ./src

RUN python -m pip install --upgrade pip && \
    python -m pip install .

ENTRYPOINT ["ado-ai-pr-review"]
