import time
class Seat:
    def __init__(self, seat_number):
        self.seat_number = seat_number
        self.status = "AVAILABLE"
        self.locked_by = None
        self.lock_time = None
        self.booking_id = None

    def lock(self, user_id):
        self.status = "LOCKED"
        self.locked_by = user_id
        self.lock_time = time.time()

    def unlock(self):
        self.status = "AVAILABLE"
        self.locked_by = None
        self.lock_time = None

    def book(self, booking_id):
        self.status = "BOOKED"
        self.booking_id = booking_id

    def release(self):
        self.status = "AVAILABLE"
        self.locked_by = None
        self.lock_time = None
        self.booking_id = None

    def is_available(self):
        return self.status == "AVAILABLE"
    def is_lock_expired(self, timeout=300):
        if self.status != "LOCKED":
            return False

        return (time.time() - self.lock_time) > timeout
     
class Bus:
    def __init__(
        self,
        bus_id,
        source,
        destination,
        departure_time,
        arrival_time,
        fare,
        total_seats
    ):
        self.bus_id = bus_id
        self.source = source
        self.destination = destination
        self.departure_time = departure_time
        self.arrival_time = arrival_time
        self.fare = fare
        self.total_seats = total_seats
        self.seats = {}

    def get_seats_for_date(self, journey_date):

        if journey_date not in self.seats:
            self.seats[journey_date] = []

            for i in range(1, self.total_seats + 1):
                self.seats[journey_date].append(Seat(i))

        return self.seats[journey_date]

    def available_seats(self, journey_date):

        seats = self.get_seats_for_date(journey_date)

        return sum(1 for seat in seats if seat.status == "AVAILABLE")
class Admin:
    def __init__(self, username, password):
        self.username = username
        self.password = password

    def login(self, username, password):
        return self.username == username and self.password == password
