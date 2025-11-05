import json
import re
import networkx as nx
import matplotlib.pyplot as plt


class CaptureTheFlagGraph:
    def __init__(self, json_path):
        with open(json_path, "r") as f:
            self.data = json.load(f)

        # Build initial graph
        self.G = nx.Graph()
        self.production_rules = {}  # e.g., {"infantry": {"cost": 3, "attack": 1, "defense": 2, ...}}
        self.victory_cities = set()
        self.unit_info = {}  # general unit metadata (range, move type, etc.)
        self.turn_number = 1

        self.pending_props = {}

        self._build_graph()
        self._load_metadata()

        #  only for display - can remove
        self.pos = nx.spring_layout(self.G, seed=42)
        self.fig, self.ax = plt.subplots(figsize=(10, 8))
        self.node_collection = nx.draw_networkx_nodes(
            self.G, self.pos, ax=self.ax,
            node_color=self._get_colors(), node_size=800
        )
        self.edge_collection = nx.draw_networkx_edges(self.G, self.pos, ax=self.ax)
        self.label_collection = nx.draw_networkx_labels(self.G, self.pos, ax=self.ax, font_size=8)

        plt.ion()
        plt.show()

    def _build_graph(self):
        # Add territories as nodes with attributes
        for territory in self.data["territories"]:
            owner = self.data["starting_ownership"].get(territory, "Neutral")
            self.G.add_node(territory, owner=owner, units=[], properties={"battle": False})       # do i need properties for a territory???

        # Add initial units
        for unit_info in self.data["starting_units"]:
            terr = unit_info["territory"]
            if terr in self.G.nodes:
                unit_entry = {
                    "unit": unit_info["unit"],
                    "owner": unit_info["owner"],
                    "quantity": unit_info["quantity"],
                    "properties": {}  # dynamic flags (e.g., has_moved, was_in_combat)
                }
                self.G.nodes[terr]["units"].append(unit_entry)

        # Add connections as edges
        for conn in self.data["connections"]:
            self.G.add_edge(conn["from"], conn["to"])

        self.G.owners = {}
        for owner, pu in self.data.get("initial_resources", {}).items():
            self.G.owners[owner] = {
                "name": owner,
                "PU": int(pu),
                "latest_loc": "", # to maintain the latest owner=territory that got updated, for logs that do not mention any territory that the unit belongs to 
                "unplaced": {}  # dict of units -> qty
            }

    def _load_metadata(self):
        # --- Load Production Rules with Unit Stats ---
        unit_stats = self.data.get("unit_stats", {})   

        for key, rule in self.data["production_rules"].items():
            unit_name = rule["unit"]
            stats = unit_stats.get(unit_name, {})      

            self.production_rules[unit_name] = {
                "cost": rule["cost"],
                "attack": stats.get("attack", 0),      
                "defense": stats.get("defense", 0),
                "move": stats.get("movement", 1),
                "type": rule.get("type", "land")
            }

        # --- Store Unit and Victory City Info ---
        self.unit_info = self.data.get("units", {})
        self.victory_cities = set(self.data.get("victory_cities", []))


    def reset(self):
        """Reset graph state to initial configuration."""
        self.G.clear()
        self._build_graph()
        self._load_metadata()
        self.turn_number = 1
        print("Graph reset complete.")


    #  only for display - can remove
    def _get_colors(self):
        colors = []
        for node in self.G.nodes:
            owner = self.G.nodes[node].get("owner", None)
            if owner == "Russians":
                colors.append("brown")
            elif owner == "Italians":
                colors.append("green")
            elif owner == "Germans":
                colors.append("blue")
            elif owner == "Chinese":
                colors.append("purple")
            else:
                colors.append("lightgray")
        return colors

    #  only for display - can remove
    def draw(self):
        border_colors = []
        labels = {}
        label_pos = {}

        # Build node colors and labels
        for node in self.G.nodes:
            owner = self.G.nodes[node].get("owner", None)
            units = self.G.nodes[node].get("units", [])

            # Border color
            if hasattr(self, "whoAmI") and owner == self.whoAmI:
                border_colors.append("gold")
            else:
                border_colors.append("black")

            # Unit label
            if units:
                unit_lines = []
                for u in units:
                    props = u.get("properties", {})
                    in_combat = str(props.get("wasInCombat", "")).lower() == "true"
                    tag = " [inCombat]" if in_combat else ""
                    unit_lines.append(f"{u['quantity']} {u['unit']} ({u['owner']}){tag}")
                labels[node] = "\n".join(unit_lines)
                x, y = self.pos[node]
                label_pos[node] = (x, y + 0.08)
            else:
                labels[node] = ""
                label_pos[node] = self.pos[node]

        
        # for territory in self.G.nodes:
        #     if self.G.nodes[territory]["properties"]["battle"]:
        #         self.G.nodes[territory]["shape"] = "octagon"
        #     else:
        #         # fallback shape if not in combat
        #         self.G.nodes[territory]["shape"] = "ellipse"



        # Update visuals
        new_colors = self._get_colors()
        self.node_collection.set_facecolor(new_colors)
        self.node_collection.set_edgecolor(border_colors)
        self.node_collection.set_linewidth(2.0)

        # self.edge_collection.set_edgecolor(edge_colors)
        # self.edge_collection.set_linewidth(3.0)
        # self.edge_collection.set_zorder(1)
        # self.node_collection.set_zorder(2)

        self.fig.set_size_inches(16, 16)

        # Remove previous labels if any
        if hasattr(self, "label_texts"):
            for txt in self.label_texts:
                txt.remove()
        self.label_texts = []

        # Draw shifted unit labels and keep references
        for node, (x, y) in label_pos.items():
            txt = self.ax.text(x, y, labels[node], fontsize=8, ha="left", va="center")
            self.label_texts.append(txt)

        if hasattr(self, "resource_text_box"):
            self.resource_text_box.remove()  # remove old box

        if hasattr(self.G, "owners"):
            lines = []
            for owner, pdata in self.G.owners.items():
                # Base line with PU
                line = f"{owner}: {pdata['PU']} PUs"

                # If unplaced units exist, append them inline
                if pdata["unplaced"]:
                    units_str = ", ".join(
                        [f"{qty} {utype}" for utype, qty in pdata["unplaced"].items()]
                    )
                    line += f" | Unplaced: {units_str}"

                lines.append(line)

            resource_text = "\n".join(lines)

            self.resource_text_box = self.ax.text(
                1.05, 0.5, resource_text, transform=self.ax.transAxes, fontsize=12,
                verticalalignment="center",
                bbox=dict(boxstyle="round,pad=0.5", facecolor="lightyellow", edgecolor="black")
            )


        self.fig.canvas.draw_idle()
        self.fig.canvas.flush_events()



    def update_my_role(self, role):
        self.whoAmI = role
        print(f"WHOAMI updated: {role}")

    def update_ownership(self, territory, new_owner):
        if territory in self.G.nodes:
            self.G.nodes[territory]["owner"] = new_owner
            self.G.owners[new_owner]["latest_loc"] = territory
            # print(f"{territory} is now owned by {new_owner}")

    def add_unit(self, territory, unit, owner, quantity=1, properties=None):
        """Add a unit to a territory or to a player's unplaced pool (purchase)."""
        if properties is None:
            properties = {}

        # --- Case 1: Territory placement ---
        if territory in self.G.nodes:
            for u in self.G.nodes[territory]["units"]:
                if u["unit"] == unit and u["owner"] == owner:
                    u["quantity"] += quantity
                    break
            else:
                self.G.nodes[territory]["units"].append({
                    "unit": unit,
                    "owner": owner,
                    "quantity": quantity,
                    "properties": properties
                })

            # Keep quick summary updated
            counts = self.G.nodes[territory].setdefault("unit_counts", {})
            counts[unit] = counts.get(unit, 0) + quantity

            # print(f"Added {quantity} {unit}(s) for {owner} in {territory}")

        # --- Case 2: Purchase (unplaced pool) ---
        elif territory in self.G.owners:
            unplaced = self.G.owners[territory]["unplaced"]
            unplaced[unit] = unplaced.get(unit, 0) + quantity
            # print(f"Purchased {quantity} {unit}(s) for {territory}")




    def remove_unit(self, territory, unit, owner, quantity=1):
        if territory in self.G.nodes:
            units = self.G.nodes[territory]["units"]
            for u in units:
                if u["unit"] == unit and u["owner"] == owner:
                    u["quantity"] -= quantity
                    if u["quantity"] <= 0:
                        units.remove(u)
                    break
            # print(f"Removed {quantity} {unit}(s) of {owner} from {territory}")

        elif territory in self.G.owners:
            unplaced = self.G.owners[territory]["unplaced"]
            unplaced[unit] = unplaced.get(unit, 0) - quantity
            # print(f"Placed {quantity} {unit}(s) for {territory}")


    def update_unit_property(self, unit, owner, prop, new_val):
        """
        Update a property for a specific unit in a territory.
        Automatically stores old value for reference.
        """
        if not hasattr(self, "pending_props"):
            self.pending_props = {}
        territory = self.G.owners[owner]["latest_loc"]
        if territory and territory in self.G.nodes:
            for u in self.G.nodes[territory]["units"]:
                if u["unit"] == unit and u["owner"] == owner:
                    old_val = u["properties"].get(prop, None)
                    u["properties"][prop] = new_val
                    # print(f"Updated {unit} ({owner}) in {territory}: {prop} changed from {old_val} to {new_val}")
                    break
            else:
                self.pending_props[prop] = new_val
                # print(f"Updated pending props: {self.pending_props}")



    def add_connection(self, from_t, to_t):
        self.G.add_edge(from_t, to_t, color="black")  # default color
        # print(f"Connection added between {from_t} and {to_t}")

    def remove_connection(self, from_t, to_t):
        if self.G.has_edge(from_t, to_t):
            self.G.remove_edge(from_t, to_t)
            # print(f"Connection removed between {from_t} and {to_t}")

    def update_pus(self, player, qty):
        self.G.owners[player]["PU"] += qty
        # print(f"Updated resources for {player}: {self.G.owners[player]["PU"]}")

    def add_battle_record(self, player, battle_id, territory):
        """
        Add a battle record to the graph.
        `battle` can include battle_id, type, and territory.
        """
        # self.G.graph.setdefault("battles", {}).setdefault(player, []).append(battle)
        self.G.nodes[territory]["properties"]["battle"] = True
        # print(f"{player}: Battle at {territory}")




    def apply_change_line(self, line: str, ispartComposite):
        line = line.strip()
        # print(f"SEARCHING  {line}")

        # --- Role assignment ---
        m = re.search(r"Role: (\w+)", line)
        if m:
            role = m.group(1)
            self.update_my_role(role)
            return

        # havent checked in composite
        if "Adding Battle Records:" in line:
            m = re.search(r"Adding Battle Records: \[(.*?)\]", line)
            if m:
                records = m.groups()
                # Split into player=battles
                for part in records:
                    if "=" in part:
                        player, battles = part.split("=", 1)
                        player = player.strip()
                        battles = battles.strip()
                        id_terr = re.findall(r"([0-9a-f]+):.*?battle in (\w+)", battles)
                        for pair in id_terr:
                            battle_id, territory = pair
                            self.add_battle_record(player, battle_id, territory)
            return

        # --- CompositeChange ---
        if "CompositeChange" in line:
            # Collect the text inside the top-level CompositeChange <[ ... ]>
            start = line.find("<[")
            if start == -1:
                return
            start += 2
            depth = 1
            inner = []
            for i in range(start, len(line)):
                if line[i:i+2] == "<[":
                    depth += 1
                    inner.append(line[i:i+2])
                    continue
                if line[i:i+2] == "]>":
                    depth -= 1
                    if depth == 0:
                        break
                    inner.append(line[i:i+2])
                    continue
                inner.append(line[i])

            inner_text = ''.join(inner)

            # Split at commas that start a new sub-change
            parts = re.split(
                r", (?=(?:Property change|Add unit change|Remove unit change|Change resource|takes |CompositeChange ))",
                inner_text
            )

            for p in parts:
                p = p.strip()
                if p:
                    self.apply_change_line(p, 1)
            return

        # --- Territory takes ---
        m = re.search(r"(\w+) takes (\w+) from (\w+)", line)
        if m:
            player, territory, old_owner = m.groups()
            self.update_ownership(territory, player)
            return

        # --- Add unit change ---
        m = re.search(r"Add unit change.*Add to: (\w+) units: \[(.+)\]", line)
        if m:
            territory, units_str = m.groups()
            units_str = units_str.strip("]>")  # remove any trailing characters
            for u in units_str.split(","):
                u = u.strip()
                m2 = re.match(r"(\w+) owned by (\w+)", u)
                if m2:
                    unit, owner = m2.groups()
                    self.add_unit(territory, unit.strip(), owner.strip())
                    if self.pending_props != {}:
                        for key in self.pending_props.keys():
                            self.update_unit_property(unit.strip(), owner.strip(), key, self.pending_props[key])
                        self.pending_props = {}
            return

        # --- Remove unit change ---
        # apart from the territories, it also tells just the owners losing the units, understand why
        m = re.search(r"Remove unit change.*Remove from: (\w+) units: \[(.+)\]", line)
        if m:
            territory, units_str = m.groups()
            units_str = units_str.strip("]>")
            for u in units_str.split(","):
                u = u.strip()
                m2 = re.match(r"(\w+) owned by (\w+)", u)
                if m2:
                    unit, owner = m2.groups()
                    self.remove_unit(territory, unit.strip(), owner.strip())
            return

        # # --- Resource change ---
        # # "Change resource"
        m = re.search(r"Resource:PUs quantity:(-?\d+) Player:(\w+)", line)
        if m:
            qty, player = m.groups()
            qty = int(qty)
            self.update_pus(player, qty)
            return

        # # --- Property change ---
        # ============================ SKIPPED since not all info is provided =======================
        m = re.search(
            r"Property change, unit:(\w+) owned by (\w+) property:(\w+) newValue:(\w+) oldValue:(\w+)", 
            line
        )
        if m:
            # Property change, unit:armour owned by Russians property:wasInCombat newValue:true oldValue:false
            unit, owner, prop, new_val, old_val = m.groups()
            self.update_unit_property(unit.strip(), owner.strip(), prop.strip(), new_val.strip())
            return

    def get_factories(self, player):
        factories = []
        for territory, data in self.G.nodes(data=True):
            for unit in data["units"]:
                if unit["owner"] == player and unit["unit"] == "factory":
                    factories.append(territory)
        return factories
    
    def get_player_resources(self, player):
        return self.G.owners[player]["PU"]
    
