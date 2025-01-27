# Bank Scraper

This is a Python-based application designed to scrape financial data from various banking and investment
platforms. It supports multiple entities and features, providing a unified interface to gather and process financial
information.

This is not actively maintained and was meant only for personal use, so some banks/entities/features/instruments may not
work, be outdated or partially implemented. That's why this documentation is so scarce.

## Table of Contents

- [Features](#features)
- [Installation](#installation)
- [Configuration](#configuration)
- [Environment Variables](#environment-variables)
- [Usage](#usage)

## Features

- Scrape financial data from multiple entities
- Support for various financial products (stocks, funds, real estate, etc.)
- Dynamic and customizable data export to Google Sheets
- Virtual scraping for simulated data

### Supported Entities

- `URBANITAE` (wallet & investments)
- `MY_INVESTOR` (periodic automatic fund contributions, funds, stocks/ETFs, main account position & related cards)
- `SEGO` (wallet & factoring)
- `TRADE_REPUBLIC` (stocks/ETFs/Crypto & account)
- `UNICJA` (main account and related cards & mortgage)
- `WECITY` (wallet & investments)
- `MINTOS` (wallet & loan distribution) (experimental)

### Entity Features

Not all entities support the same features. Some or all of the following features are available for each entity:

- `POSITION`: Fetch the current financial position.
- `AUTO_CONTRIBUTIONS`: Fetch the auto-contributions of the entity.
- `TRANSACTIONS`: Fetches all the account/investment transactions.
- `HISTORIC`: Aggregates past positions and txs to create a history of past and current investments.

## Setup

1. Clone the repository:
    ```sh
    git clone https://github.com/marcosav/bank-scraper.git
    cd bank-scraper
    ```

2. Create a virtual environment and activate it:
    ```sh
    python3 -m venv venv
    source venv/bin/activate
    ```

3. Install the required dependencies:
    ```sh
    pip install -r requirements.txt
    ```

## Configuration

Checkout the default (template_config.yml) config that will be created on first start.

## Environment Variables

Checkout example docker-compose.yml for the environment variables that can be used to override the default config, set
Mongo connection related stuff, Google credentials, entity session caches...

Also, credentials_reader.py is a basic and unsecure implementation to retrieve credentials from environments, there you
can get the needed environment names.

## Usage

1. Start the application:
    ```sh
    python app.py
    ```

2. Use the provided API endpoints to interact with the scraper:
    - `GET /api/v1/scrape`: Get available entities.
    - `POST /api/v1/scrape`: Start a scraping process for a specific entity.
    - `POST /api/v1/update-sheets`: Update Google Sheets with the latest data.
    - `POST /api/v1/scrape/virtual`: Perform a virtual scrape.