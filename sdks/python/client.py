#!/usr/bin/python

import sys
import json
import time
import random

if sys.version_info > (3, 0):
    import socketserver as ss
else:
    import SocketServer as ss


class NetworkHandler(ss.StreamRequestHandler):
    def handle(self):
        game = Game()
        while True:
            data = self.rfile.readline().decode()
            if not data:
                break
            json_data = json.loads(data)
            response = game.get_move(json_data).encode()
            self.wfile.write(response)


class Game:
    def __init__(self):
        self.base_location = None
        self.resource_list = []  # Track visible resources
        self.directions = {'N', 'S', 'E', 'W'}
        self.start_time = time.time()
        self.units = {}  # Store unit states persistently

    def get_move(self, json_data):
        unit_updates = json_data.get('unit_updates', [])
        self.set_base_location(unit_updates)
        self.update_units(unit_updates)  # Update existing units or add new ones
        commands = []

        elapsed_time = time.time() - self.start_time

        for unit_id, unit in self.units.items():
            if unit['type'] == 'base' or unit['status'] == 'dead':
                continue

            # For the first 30 seconds, move randomly and try to gather in all directions
            if elapsed_time < 30:
                direction = self.get_random_direction(unit)
                if direction:
                    commands.append({"command": "MOVE", "unit": unit_id, "dir": direction})
                
                # Attempt to gather resources in all directions
                for gather_direction in self.directions:
                    commands.append({"command": "GATHER", "unit": unit_id, "dir": gather_direction})
            
            else:
                # After 30 seconds, return to base and drop resources
                if self.base_location and (unit['x'], unit['y']) != self.base_location:
                    # Move towards the base
                    direction = self.get_move_direction(unit, self.base_location)
                    if direction:
                        commands.append({"command": "MOVE", "unit": unit_id, "dir": direction})

        return json.dumps({"commands": commands}, separators=(',', ':')) + '\n'

    def update_units(self, unit_updates):
        """Update the state of units with new data from unit_updates."""
        # Update units with new positions and states
        for update in unit_updates:
            unit_id = update['id']
            self.units[unit_id] = update  # Store the latest information for each unit

        # Retain previous state for units not in the current update

    def set_base_location(self, units):
        """Locate and set the base if not yet set."""
        if not self.base_location:
            for unit in units:
                if unit['type'] == 'base':
                    self.base_location = (unit['x'], unit['y'])
                    break

    def get_random_direction(self, unit):
        """Select a random available direction for movement."""
        return random.choice(['N', 'S', 'E', 'W'])

    def get_move_direction(self, unit, target):
        """Calculate the direction for the unit to move toward the target."""
        unit_x, unit_y = unit['x'], unit['y']
        target_x, target_y = target
        if unit_x < target_x:
            return 'E'
        elif unit_x > target_x:
            return 'W'
        elif unit_y < target_y:
            return 'S'
        elif unit_y > target_y:
            return 'N'
        return None


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9090
    host = '0.0.0.0'
    server = ss.TCPServer((host, port), NetworkHandler)
    print(f"Listening on {host}:{port}")
    server.serve_forever()
