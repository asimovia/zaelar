"""`python -m voice.engine` — the voice in its own process (V2-891). Started by the body (`voice/child_process.py`),
which hands it its port, the body's address and the token; see `voice/engine/pipeline/child.py`."""
from voice.engine.pipeline.child import main

if __name__ == "__main__":
    main()
