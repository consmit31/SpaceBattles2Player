#!/usr/bin/python

import sys
import json
import heapq
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
                break  # Exit if no data is received
            json_data = json.loads(data)
            print("Received data:", json_data)  # Debug print to inspect incoming JSON data
            
            response = game.get_move(json_data).encode()
            print("Sending response:", response.decode())  # Debug print to inspect outgoing response
            self.wfile.write(response)


class Tile:
    def __init__(self, x, y, blocked=False, resources=None, visible=False):
        self.x = x
        self.y = y
        self.blocked = blocked
        self.resources = resources
        self.visible = visible


class Game:
    def __init__(self):
        self.units = {}
        self.map = []
        self.map_width = 0
        self.map_height = 0
        self.base_location = None
        self.directions = {'N': (-1, 0), 'S': (1, 0), 'E': (0, 1), 'W': (0, -1)}
        self.initialized = False  # Track if game_info has been initialized

    def build_map(self, json_data):
        # Only initialize map on turn 0 when game_info is present
        game_info = json_data.get('game_info')
        if game_info and not self.initialized:
            self.map_width = game_info.get('map_width', 0)
            self.map_height = game_info.get('map_height', 0)
            self.map = [[None for _ in range(self.map_width)] for _ in range(self.map_height)]
            self.initialized = True  # Set initialized to True after the first setup
            print("Game initialized with map size:", self.map_width, "x", self.map_height)

        tiles = json_data.get('tile_updates', [])
        
        for tile in tiles:
            x, y = tile['x'], tile['y']
            self.map[y][x] = Tile(
                x=x,
                y=y,
                blocked=tile.get('blocked', False),  # Default to False if 'blocked' is missing
                resources=tile.get('resources'),
                visible=tile.get('visible', False)
            )

    def a_star_pathfind(self, start, goal):
        """A* pathfinding algorithm to find path from start to goal around blocked tiles."""
        open_set = [(0, start)]
        came_from = {}
        g_score = {start: 0}
        f_score = {start: self.heuristic(start, goal)}
        visited = set()

        while open_set:
            _, current = heapq.heappop(open_set)
            if current == goal:
                return self.reconstruct_path(came_from, current)

            visited.add(current)

            for direction in self.directions.values():
                neighbor = (current[0] + direction[1], current[1] + direction[0])
                x, y = neighbor
                if 0 <= x < self.map_width and 0 <= y < self.map_height:
                    tile = self.map[y][x]
                    if tile and not tile.blocked and neighbor not in visited:
                        tentative_g_score = g_score[current] + 1

                        if neighbor not in g_score or tentative_g_score < g_score[neighbor]:
                            came_from[neighbor] = current
                            g_score[neighbor] = tentative_g_score
                            f_score[neighbor] = tentative_g_score + self.heuristic(neighbor, goal)
                            heapq.heappush(open_set, (f_score[neighbor], neighbor))

        return None  # No path found

    def heuristic(self, a, b):
        """Manhattan distance heuristic for A* pathfinding."""
        return abs(a[0] - b[0]) + abs(a[1] - b[1])

    def reconstruct_path(self, came_from, current):
        """Reconstruct path from A* pathfinding result."""
        path = []
        while current in came_from:
            path.append(current)
            current = came_from[current]
        path.reverse()
        return path

    def get_move_direction(self, unit, target):
        """Get the direction for the unit to move towards the next step in the path."""
        unit_x, unit_y = unit['x'], unit['y']
        path = self.a_star_pathfind((unit_x, unit_y), target)
        if path and len(path) > 1:
            next_step = path[1]
            dx = next_step[0] - unit_x
            dy = next_step[1] - unit_y
            for direction, (d_y, d_x) in self.directions.items():
                if dx == d_x and dy == d_y:
                    return direction
        return None

    def get_random_direction(self, unit):
        """Choose a random direction for wandering."""
        x, y = unit['x'], unit['y']
        random_directions = list(self.directions.items())
        random.shuffle(random_directions)

        for direction, (dy, dx) in random_directions:
            nx, ny = x + dx, y + dy
            if 0 <= nx < self.map_width and 0 <= ny < self.map_height:
                tile = self.map[ny][nx]
                if tile and not tile.blocked:
                    return direction
        return None

    def get_move(self, json_data):
        # Build or update the map
        self.build_map(json_data)

        units = json_data.get('unit_updates', [])
        commands = []

        for unit in units:
            if unit['type'] == 'base' or unit['status'] == 'dead':
                continue

            unit_id = unit['id']
            unit_state = self.units.get(unit_id, {}).get('state', 'wander')
            self.units[unit_id] = {"state": unit_state}

            if unit_state == 'return' and unit['resource'] > 0:
                direction = self.get_move_direction(unit, self.base_location)
                if direction:
                    commands.append({"command": "MOVE", "unit": unit_id, "dir": direction})
                    continue
                self.units[unit_id]['state'] = 'wander'

            elif unit_state == 'wander' and unit['resource'] == 0:
                # Check adjacent tiles for resources
                resource_found = False
                for direction, (dy, dx) in self.directions.items():
                    nx, ny = unit['x'] + dx, unit['y'] + dy
                    if 0 <= nx < self.map_width and 0 <= ny < self.map_height:
                        tile = self.map[ny][nx]
                        if tile and tile.resources:
                            commands.append({"command": "GATHER", "unit": unit_id, "dir": direction})
                            self.units[unit_id]['state'] = 'return'
                            resource_found = True
                            break

                # If no resource is found, move randomly
                if not resource_found:
                    direction = self.get_random_direction(unit)
                    if direction:
                        commands.append({"command": "MOVE", "unit": unit_id, "dir": direction})

        response = json.dumps({"commands": commands}, separators=(',', ':')) + '\n'
        return response


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 9090
    host = '0.0.0.0'

    server = ss.TCPServer((host, port), NetworkHandler)
    print(f"Listening on {host}:{port}")
    server.serve_forever()
