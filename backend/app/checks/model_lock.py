"""One model loads at a time. MIRA and the owner's trained model load in background threads at server start; when
both imported the transformers library at the same moment, MIRA failed with an ImportError. This lock makes them
load one after the other (only loading - answering questions is not locked)."""
import threading

LOAD_LOCK = threading.Lock()
