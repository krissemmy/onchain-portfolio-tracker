# Onchain-portfolio-tracker
A fast, minimal UI for tracking token balances across multiple EVM wallets and Solana/Eclipse wallets

## Setup
### Environment Variables

Create a .env:
```bash
echo "SIM_API_KEY=YOUR_API_KEY_FROM_DUNE_SIM" > .env
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
- EVM
    - GET `https://api.sim.dune.com/v1/wallet/{address}/balances`
    - GET `https://api.sim.dune.com/v1/wallet/{address}/activity`

- SVM
    - GET `https://api.sim.dune.com/beta/svm/balances/{address}`

> SVM activity is not yet supported by Dune Sim.

