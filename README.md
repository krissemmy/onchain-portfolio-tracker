# Onchain-portfolio-tracker
A fast, minimal UI for tracking token balances across multiple EVM wallets and Solana/Eclipse wallets

## Setup
### Environment Variables

Create a .env:
```bash
echo "ZERION_API_KEY=YOUR_API_KEY_FROM_ZERION" > .env
```

## Running the App
#### Install dependencies

You need uv (ultra-fast Python runner):
```bash
pip install uv
```

Run the server:
```bash
uv run uvicorn main:app --reload --port 3001
```

Then open:
```
http://localhost:3001
```

### API Endpoints Used
- EVM/SVM
    - GET `https://api.zerion.io/v1/wallets/{address}/positions/`
    - GET `https://api.zerion.io/v1/wallets/{address}/transactions/`

What if u can track ur total portfolio......across all wallet address u own? EVM, SVM e.t.c. and just have one UI that tells u ur current holdings in crypto, including the PnL for that day?



Built with Python FastAPI + Zerion API.



Try it here: https://portfolio.krissemmy.com

Github repo: https://github.com/krissemmy/onchain-portfolio-tracker



#Blockchain #DataEngineering #Web3Analytics #DeFi #onchain

l3arn

-⁠  ⁠A complete product end-to-end, which is an alternative to Postman for developers: https://krainode.krissemmy.com, https://github.com/krissemmy/krainode-rpc-proxy

-⁠  ⁠Onchain portfolio tracker(it allows u to see the total holdings of ur crypto from all ur wallet):  https://portfolio.krissemmy.com, https://github.com/krissemmy/onchain-portfolio-tracker

-⁠  ⁠A benchmarking analytics tool to test the performance of a Blockchain API endpoint: https://rpc.benchmark.krissemmy.com/, https://github.com/krissemmy/evm-node-rpc-benchmark

-⁠  ⁠Complete monitoring Architecture deployment using Kubernetes: https://github.com/krissemmy/monitoring-architecture-with-kubernetes

-⁠  ⁠End-to-end ETL pipeline using dlt framework: https://github.com/krissemmy/ETL-with-dlt

-⁠  ⁠ELT Pipeline with Airflow, SQL, dbt, Docker, e.t.c using Finance data with clear guidance for both technical and non-technical stakeholders: https://github.com/krissemmy/Polygon-Finance-Data-ELT
