import threading
import copy
import time
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
        self.last_merge_allocations = None
        self.passenger_notifications = {}
        
        # Session timeout management (60 seconds session timeout)
        self.active_sessions = {}
        self.session_timeout = 60
        self.session_checker_thread = threading.Thread(target=self.check_session_timeouts)
        self.session_checker_thread.daemon = True
        self.session_checker_thread.start()

    def register_login(self, visitor_id, role):
        with self.lock:
            self.active_sessions[visitor_id] = {
                'role': role,
                'last_activity': time.time()
            }

    def register_activity(self, visitor_id, role):
        with self.lock:
            self.active_sessions[visitor_id] = {
                'role': role,
                'last_activity': time.time()
            }

    def register_logout(self, visitor_id):
        with self.lock:
            self.active_sessions.pop(visitor_id, None)

    def is_session_active(self, visitor_id):
        with self.lock:
            return visitor_id in self.active_sessions

    def check_session_timeouts(self):
        while True:
            time.sleep(5)
            now = time.time()
            timed_out_users = []
            with self.lock:
                for visitor_id, session in list(self.active_sessions.items()):
                    if now - session['last_activity'] > self.session_timeout:
                        timed_out_users.append((visitor_id, session['role']))
                        self.active_sessions.pop(visitor_id, None)
            
            for visitor_id, role in timed_out_users:
                self.logger.log(f"{role.capitalize()} '{visitor_id}' automatically logged out (session inactive/closed)")

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
        self.last_merge_allocations = None
        self.passenger_notifications = {}
        self.logger.log("Merge undone, previous bus state restored")
        return "Merge undone successfully"

    def get_low_load_buses_for_route_and_date(self, source, destination, journey_date):
        low_buses = []
        for bus in self.buses.values():
            if bus.source == source and bus.destination == destination:
                seats = bus.get_seats_for_date(journey_date)
                total = len(seats)
                booked = sum(1 for seat in seats if seat.status == "BOOKED")
                if total > 0:
                    load = booked / total
                    if load < 0.2:
                        low_buses.append(bus.bus_id)
        return low_buses

    def find_next_available_seat(self, dest_seats, seat_num):
        idx = seat_num - 1
        row_start = (idx // 4) * 4
        row_indices = [row_start, row_start + 1, row_start + 2, row_start + 3]
        
        # 1. Immediate neighbor in the same row
        neighbor_idx = idx ^ 1
        if neighbor_idx in row_indices and dest_seats[neighbor_idx].status == "AVAILABLE":
            return neighbor_idx
            
        # 2. Other seats in the same row
        for r_idx in row_indices:
            if r_idx != idx and dest_seats[r_idx].status == "AVAILABLE":
                return r_idx
                
        # 3. Row behind / front
        for offset in [4, -4, 8, -8]:
            target_idx = idx + offset
            if 0 <= target_idx < len(dest_seats) and dest_seats[target_idx].status == "AVAILABLE":
                return target_idx
                
        # 4. Any other seat in the bus
        for i in range(len(dest_seats)):
            if dest_seats[i].status == "AVAILABLE":
                return i
                
        return None

    def search_buses(self, source, destination):
        return [
            bus for bus in self.buses.values()
            if bus.source == source and bus.destination == destination
        ]

    def get_all_places(self):
        sources = sorted({bus.source for bus in self.buses.values()})
        destinations = sorted({bus.destination for bus in self.buses.values()})
        return sources, destinations

    def _add_passenger_notification(self, passenger, journey_date, source, destination,
                                    original_bus, original_seat, new_bus, new_seat):
        if original_seat == new_seat:
            return

        message = (
            f"Your seat was changed due to a bus merge on {journey_date} "
            f"({source} → {destination}). You were moved from Bus {original_bus} "
            f"Seat {original_seat} to Bus {new_bus} Seat {new_seat}."
        )

        notification = {
            "message": message,
            "journey_date": journey_date,
            "source": source,
            "destination": destination,
            "original_bus": original_bus,
            "original_seat": original_seat,
            "new_bus": new_bus,
            "new_seat": new_seat,
        }
        self.passenger_notifications.setdefault(passenger, []).append(notification)
        self.logger.log(f"Notified passenger {passenger}: {message}")

    def get_notifications_for_passenger(self, passenger):
        return list(self.passenger_notifications.get(passenger, []))

    def clear_notifications_for_passenger(self, passenger):
        self.passenger_notifications.pop(passenger, None)

    def get_bookings_for_bus(self, bus_id, journey_date):
        bus = self.buses.get(bus_id)
        if not bus:
            return []
        seats = bus.get_seats_for_date(journey_date)
        bookings = []
        for seat in seats:
            if seat.status == "BOOKED" and seat.booked_by:
                bookings.append({
                    "seat_number": seat.seat_number,
                    "passenger": seat.booked_by,
                    "booking_id": seat.booking_id,
                })
        return sorted(bookings, key=lambda b: b["seat_number"])

    def merge_buses_for_route_and_date(self, source, destination, journey_date):
        low_buses = self.get_low_load_buses_for_route_and_date(source, destination, journey_date)

        if len(low_buses) < 2:
            return "Not enough low-load buses to merge on this route for this date"

        with self.lock:
            # Save the current state of buses for undoing
            self.last_merged_state = copy.deepcopy(self.buses)
            
            # Select the destination bus (e.g. the first one)
            dest_bus_id = low_buses[0]
            dest_bus = self.buses[dest_bus_id]
            dest_seats = dest_bus.get_seats_for_date(journey_date)
            
            self.last_merge_allocations = []
            
            # Keep track of passengers already in the destination bus
            for seat in dest_seats:
                if seat.status == "BOOKED":
                    self.last_merge_allocations.append({
                        "passenger": seat.booked_by,
                        "original_bus": dest_bus_id,
                        "original_seat": seat.seat_number,
                        "new_bus": dest_bus_id,
                        "new_seat": seat.seat_number,
                        "status": "Kept original seat"
                    })
            
            source_bus_ids = low_buses[1:]
            self.merge_alert_buses = set(low_buses)
            
            self.logger.log(f"Bus alteration started for {source} -> {destination} on {journey_date}")
            
            for src_id in source_bus_ids:
                src_bus = self.buses[src_id]
                src_seats = src_bus.get_seats_for_date(journey_date)
                
                for seat in src_seats:
                    if seat.status == "BOOKED":
                        passenger = seat.booked_by
                        original_seat = seat.seat_number
                        
                        # Check dest seat status
                        dest_seat = dest_seats[original_seat - 1]
                        if dest_seat.status == "AVAILABLE":
                            # Book in dest_bus
                            dest_seat.status = "BOOKED"
                            dest_seat.booking_id = seat.booking_id
                            dest_seat.booked_by = passenger
                            dest_seat.locked_by = None
                            
                            self.last_merge_allocations.append({
                                "passenger": passenger,
                                "original_bus": src_id,
                                "original_seat": original_seat,
                                "new_bus": dest_bus_id,
                                "new_seat": original_seat,
                                "status": "Moved to same seat in merged bus"
                            })
                            self.logger.log(f"Passenger {passenger} moved to Seat {original_seat} in {dest_bus_id}")
                        else:
                            # Collision! Find next available seat
                            new_seat_idx = self.find_next_available_seat(dest_seats, original_seat)
                            if new_seat_idx is not None:
                                new_seat_num = new_seat_idx + 1
                                dest_seats[new_seat_idx].status = "BOOKED"
                                dest_seats[new_seat_idx].booking_id = seat.booking_id
                                dest_seats[new_seat_idx].booked_by = passenger
                                dest_seats[new_seat_idx].locked_by = None
                                
                                self.last_merge_allocations.append({
                                    "passenger": passenger,
                                    "original_bus": src_id,
                                    "original_seat": original_seat,
                                    "new_bus": dest_bus_id,
                                    "new_seat": new_seat_num,
                                    "status": f"Reassigned due to collision (was Seat {original_seat})"
                                })
                                self._add_passenger_notification(
                                    passenger, journey_date, source, destination,
                                    src_id, original_seat, dest_bus_id, new_seat_num
                                )
                                self.logger.log(f"Passenger {passenger} reassigned from Seat {original_seat} to Seat {new_seat_num} in {dest_bus_id}")
                            else:
                                self.logger.log(f"Seat collision: No available seats in {dest_bus_id} for passenger {passenger}")
                                return f"Merge failed: Not enough seats in {dest_bus_id}"
                
                # Remove the merged source bus from system
                self.buses.pop(src_id)
                self.logger.log(f"Bus {src_id} merged into {dest_bus_id}")

            self.merge_alert_buses = set()
            return f"Merged low-load buses into {dest_bus_id}"
    
    