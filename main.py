import psutil
import os
import time
from models import Bus, Admin
from booking_manager import BookingManager
import threading

manager = BookingManager()
admin = Admin("admin", "zoho123")

if admin.login("admin", "zoho123"):
    print("Admin Login Successful")
else:
    print("Invalid Admin Credentials")

journey_date1 = "2026-07-01"
journey_date2 = "2026-07-02"

manager.add_visitor()
print("Visitors:", manager.show_visitor_count())

for i in range(1, 11):
    bus = Bus(f"BUS{i:03}", 40)
    manager.add_bus(bus)

# Demonstration of Backend Features

journey_date = "2026-07-01"

# Book one seat
print(manager.select_seat("BUS001", journey_date, 5, "Alice"))
print(manager.book_seat("BUS001", journey_date, 5, "Alice", "B001"))

# Show bus information
print("\nTotal buses:", len(manager.buses))

# Show system usage
process = psutil.Process(os.getpid())

cpu = psutil.cpu_percent(interval=1)
idle_cpu = 100 - cpu 
memory = process.memory_info()

physical_memory = memory.rss / 1024 / 1024
virtual_memory = memory.vms / 1024 / 1024

print("\n===== SYSTEM METRICS =====")
print(f"CPU Usage: {cpu}%")
print(f"CPU Idle Time: {idle_cpu}%")
print(f"Physical Memory (RSS): {physical_memory:.2f} MB")
print(f"Virtual Memory (VMS): {virtual_memory:.2f} MB")
print("==========================")