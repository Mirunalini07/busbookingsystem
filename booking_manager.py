import threading
import copy
from logger import Logger
from models import Bus

INITIAL_BUSES = 10
MAX_BUSES = 100
BUSES_TO_ADD = 2
LOAD_THRESHOLD = 0.8
SEATS_PER_BUS = 40

class BookingManager:
    def __init__(self):
        self.buses = {} #This is a dictionary to store all buses.
        self.logger = Logger()
        self.lock = threading.Lock()
        self.visitor_count = 0
        self.last_merged_state = None
        self.merge_alert_buses = set()

    def add_bus(self, bus):
        self.buses[bus.bus_id] = bus
    def select_seat(self, bus_id,journey_date, seat_number, user_id):
        bus = self.buses.get(bus_id)

        if not bus:
            return "Bus not found"
        seats = bus.get_seats_for_date(journey_date)
        seat = seats[seat_number - 1]
        with self.lock:
        # NEW: check expiry first
            self._check_and_unlock(seat)

            if not seat.is_available():   #Check availability
                return "Seat not available"

            seat.lock(user_id)
            self.logger.log(f"{user_id} locked seat {seat_number} in bus {bus_id}")
        return "Seat locked successfully"
    
    def book_seat(self, bus_id, journey_date, seat_number, user_id, booking_id):
        bus = self.buses.get(bus_id)   #Find the correct bus

        if not bus:
            return "Bus not found"

        seats = bus.get_seats_for_date(journey_date)
        seat = seats[seat_number - 1]

        with self.lock:  # safety check
            if seat.locked_by != user_id:     #Only the person who locked it can confirm booking
                return "You must lock the seat first"

            seat.book(booking_id, user_id)
            self.logger.log(f"{user_id} booked seat {seat_number} in bus {bus_id}")
            self.add_extra_buses_if_needed()
        return "Seat booked successfully"
    
    def cancel_booking(self, bus_id,journey_date, seat_number, user_id):
        bus = self.buses.get(bus_id)

        if not bus:
            return "Bus not found"

        seats = bus.get_seats_for_date(journey_date)
        seat = seats[seat_number - 1]

        with self.lock:
            if seat.status == "LOCKED" and seat.locked_by == user_id:
                seat.release()
            elif seat.status == "BOOKED" and getattr(seat, "booked_by", None) == user_id:
                seat.release()
            else:
                return "You cannot cancel this seat"

            self.logger.log(f"{user_id} cancelled seat {seat_number} in bus {bus_id}")
        return "Booking cancelled successfully"
    def _check_and_unlock(self, seat):
        if seat.is_lock_expired():
            seat.unlock()
            self.logger.log(f"Seat {seat.seat_number} auto-unlocked due to timeout")
    
    def add_visitor(self):
        self.visitor_count += 1

    def show_visitor_count(self):
        return self.visitor_count
    def calculate_load_factor(self):
        total_seats = 0
        booked_seats = 0

        for bus in self.buses.values():

            for seats in bus.seats.values():
                total_seats += len(seats)

                for seat in seats:
                    if seat.status == "BOOKED":
                        booked_seats += 1

        if total_seats == 0:
            return 0

        return booked_seats / total_seats

    def add_extra_buses_if_needed(self):
        load_factor = self.calculate_load_factor()

        if load_factor < LOAD_THRESHOLD:
            return
        current_bus_count = len(self.buses)
        for i in range(BUSES_TO_ADD):

            if len(self.buses) >= MAX_BUSES:
                break

            bus_number = len(self.buses) + 1
            bus = Bus(f"BUS{bus_number:03}", SEATS_PER_BUS)

            self.add_bus(bus)

            self.logger.log(f"New bus added: {bus.bus_id}")
            
    def get_low_load_buses(self):
        low_buses = []

        for bus in self.buses.values():
            total = 0
            booked = 0

            for seats in bus.seats.values():
                total += len(seats)
                for seat in seats:
                    if seat.status == "BOOKED":
                        booked += 1

            if total > 0:
                load = booked / total
                if load < 0.2:
                    low_buses.append(bus.bus_id)

        return low_buses
    def merge_buses(self):
        low_buses = self.get_low_load_buses()

        if len(low_buses) < 2:
            return "Not enough buses to merge"

        self.last_merged_state = copy.deepcopy(self.buses)
        destination_bus_id = low_buses[0]
        destination_bus = self.buses[destination_bus_id]
        self.merge_alert_buses = set(low_buses)

        source_bus_ids = low_buses[1:]

        self.logger.log("Bus alteration in process")
        self.merge_alert_buses = set(low_buses)
        for src_id in source_bus_ids:
            src_bus = self.buses[src_id]
            for journey_date, seats in src_bus.seats.items():
                dest_seats = destination_bus.get_seats_for_date(journey_date)
                for i, seat in enumerate(seats):
                    if seat.status == "BOOKED":
                        if dest_seats[i].status == "AVAILABLE":
                            dest_seats[i].status = "BOOKED"
                            dest_seats[i].booking_id = seat.booking_id
                            dest_seats[i].booked_by = getattr(seat, "booked_by", None)
                            dest_seats[i].locked_by = None
                        else:
                            self.logger.log(
                                f"Seat collision while merging {src_id} -> {destination_bus_id}"
                            )
            self.buses.pop(src_id)
            self.logger.log(f"Bus {src_id} merged into {destination_bus_id}")

        self.merge_alert_buses = set()
        return f"Merged into {destination_bus_id}"

    def can_undo_merge(self):
        return self.last_merged_state is not None

    def undo_merge(self):
        if not self.last_merged_state:
            return "No merge to undo"

        self.buses = self.last_merged_state
        self.last_merged_state = None
        self.merge_alert_buses = set()
        self.logger.log("Merge undone, previous bus state restored")
        return "Merge undone successfully"
    
    