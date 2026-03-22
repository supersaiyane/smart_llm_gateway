import time

def is_available(r, server, timeout):
    key = f"server:{server}"

    circuit_open = int(r.hget(key, "circuit_open") or 0)
    last_failure = float(r.hget(key, "last_failure") or 0)

    # 🔴 If circuit is OPEN
    if circuit_open == 1:
        # ⏳ Check if timeout passed → allow retry (HALF-OPEN)
        if time.time() - last_failure > timeout:
            # Allow one retry attempt
            return True
        else:
            # Still blocked
            return False

    # 🟢 Circuit is CLOSED → normal flow
    return True