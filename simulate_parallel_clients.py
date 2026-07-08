import threading
import time
import random
from app import app, manager


def login_user_session(client_id: int):
    client = app.test_client()
    response = client.post(
        "/login",
        data={"role": "user"},
        follow_redirects=True,
    )
    print(f"[User-{client_id}] logged in: {response.status_code}")
    return client


def book_seat(client, bus_id: str, seat_number: int, journey_date: str = "2026-07-01"):
    resp = client.get(f"/seats/{bus_id}?date={journey_date}")
    print(f"[Booking] GET /seats/{bus_id} status={resp.status_code}")

    lock_resp = client.post(
        f"/seat-action/{bus_id}/{seat_number}",
        data={"action": "lock", "journey_date": journey_date},
        follow_redirects=True,
    )
    print(f"[Booking] lock seat {seat_number} -> {lock_resp.status_code}")

    book_resp = client.post(
        f"/seat-action/{bus_id}/{seat_number}",
        data={"action": "book", "journey_date": journey_date},
        follow_redirects=True,
    )
    print(f"[Booking] book seat {seat_number} -> {book_resp.status_code}")
    return book_resp


def user_thread(client_id: int, bus_id: str, seat_number: int):
    client = login_user_session(client_id)
    time.sleep(random.uniform(0.1, 0.4))
    book_resp = book_seat(client, bus_id, seat_number)
    if b"Invalid booking action" in book_resp.data:
        print(f"[User-{client_id}] booking failed: invalid action")


def admin_merge_thread():
    admin_client = app.test_client()
    resp = admin_client.post(
        "/login",
        data={"role": "admin", "username": "admin", "password": "zoho123"},
        follow_redirects=True,
    )
    print(f"[Admin] login status={resp.status_code}")
    time.sleep(0.25)
    merge_resp = admin_client.post("/merge-buses", follow_redirects=True)
    merge_text = merge_resp.data.decode(errors="ignore")
    print(f"[Admin] merge status={merge_resp.status_code}")
    if "Merged into" in merge_text:
        print(f"[Admin] merge completed")
    else:
        print(f"[Admin] merge response missing merge text")


def run_simulation():
    bus_id = "BUS001"
    seat_numbers = [1, 2, 3, 4]
    threads = []

    for idx, seat_num in enumerate(seat_numbers, start=1):
        thread = threading.Thread(target=user_thread, args=(idx, bus_id, seat_num))
        threads.append(thread)
        thread.start()

    admin_thread = threading.Thread(target=admin_merge_thread)
    threads.append(admin_thread)
    admin_thread.start()

    for thread in threads:
        thread.join()

    print("\nSimulation complete")
    print(f"Current merge-alert buses: {manager.merge_alert_buses}")
    print(f"Can undo merge: {manager.can_undo_merge()}")


if __name__ == "__main__":
    run_simulation()
