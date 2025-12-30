# Forex Trading Agent (Shadow Mode)

A disciplined, risk-aware Forex trading agent designed for the EUR/USD pair. This agent operates in "Shadow Mode," simulating trades and logging decisions without risking real capital.

## 🚀 Key Features
- **Modular Architecture**: Independent modules for Data, Signals, Risk, and Execution.
- **Risk First**: Strict Risk Manager that validates every trade proposal against hard constraints.
- **Multi-Signal Logic**: Combines Trend (MA), Momentum (RSI), and Volatility (ATR) signals.
- **Real-Time Dashboard**: Streamlit-based UI for monitoring market data, signals, and audit logs.
- **Immutable Audit Logs**: Every decision and risk check is logged to `logs/audit.json`.

## 📂 Project Structure
```
├── config.yaml             # Main configuration (Risk limits, Pairs)
├── logs/                   # Generated logs and audit files
│   ├── agent.log           # Human-readable system logs
│   ├── audit.json          # Structured machine-readable event logs
│   └── market_data.csv     # Latest market snapshot for UI
├── src/
│   ├── main.py             # Agent entry point (Scheduler)
│   ├── core/               # Config, Logger, Types
│   ├── modules/            # Logic Modules
│   │   ├── market/         # Data Fetching & Indicators
│   │   ├── signals/        # Signal Generators
│   │   ├── news/           # News Interpreter (Mock)
│   │   ├── decision/       # Signal Aggregation Engine
│   │   ├── risk/           # Risk Management Rules
│   │   └── execution/      # Shadow Execution Engine
│   └── ui/                 # Streamlit Dashboard
└── verify_setup.py         # Verification Script
```

## 🛠️ Setup & Installation

1. **Prerequisites**: Python 3.9+
2. **Install Dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

## 🏃‍♂️ How to Run

### 1. Start the Agent
The agent runs in a continuous loop (scheduled every hour by default, customizable in `src/main.py`).
```bash
python3 src/main.py
```
*You will see logs indicating "Tick Start", Decision logic, and "Tick End".*

### 2. Start the Dashboard UI
Open a new terminal window and run:
```bash
python3 -m streamlit run src/ui/dashboard.py
```
*Access the dashboard at http://localhost:8501*

## ⚙️ Configuration
Edit `config.yaml` to adjust settings:
- **System**: Change `currency_pair` or `log_level`.
- **Risk**: Adjust `max_risk_per_trade` (default 1%) or `daily_loss_cap`.
- **Data**: Switch `source` between `mock` (for testing) and `yfinance` (for real data - requires fixing yfinance API access if unstable).

## 📊 Current Status
- **Phase 1 (Core)**: ✅ Complete. Logic pipeline verified with mock data.
- **Phase 2 (UI)**: ✅ Complete. Dashboard visualizes data and logs.
- **Phase 3 (Paper Trading)**: ⏳ Planned. Connecting to a real broker API.
