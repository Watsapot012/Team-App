import json
from pathlib import Path
from wsgiref.simple_server import make_server


class Menu:
    def __init__(self, file_path):
        self._file_path = Path(file_path)
        self._items = []
        self._load()

    def _load(self):
        # โหลดเมนูเดิมจาก JSON หรือสร้างไฟล์ว่างเมื่อเปิดใช้ครั้งแรก
        if not self._file_path.exists():
            self._save()
            return

        try:
            with self._file_path.open("r", encoding="utf-8") as file:
                items = json.load(file)
        except json.JSONDecodeError as error:
            raise ValueError("ไฟล์ menu.json มีรูปแบบ JSON ไม่ถูกต้อง") from error

        if not isinstance(items, list):
            raise ValueError("ข้อมูลใน menu.json ต้องเป็นรายการเมนู")

        for item in items:
            if (
                not isinstance(item, dict)
                or not isinstance(item.get("name"), str)
                or not isinstance(item.get("price"), (int, float))
                or item["price"] <= 0
            ):
                raise ValueError("ข้อมูลเมนูใน menu.json ไม่ถูกต้อง")

        self._items = items

    def _save(self):
        with self._file_path.open("w", encoding="utf-8") as file:
            json.dump(self._items, file, ensure_ascii=False, indent=2)

    def add_menu(self, name, price):
        name = name.strip()
        if not name:
            raise ValueError("กรุณาระบุชื่ออาหาร")

        try:
            price = float(price)
        except (TypeError, ValueError) as error:
            raise ValueError("ราคาต้องเป็นตัวเลข") from error

        if price <= 0:
            raise ValueError("ราคาต้องมากกว่า 0")
        if any(item["name"].casefold() == name.casefold() for item in self._items):
            raise ValueError("มีเมนูชื่อนี้อยู่แล้ว")

        self._items.append({"name": name, "price": price})
        self._save()

    def remove_menu(self, name):
        menu_item = next(
            (item for item in self._items if item["name"] == name), None
        )
        if menu_item is None:
            raise ValueError("ไม่พบเมนูที่ต้องการลบ")

        self._items.remove(menu_item)
        self._save()

    def get_menu_items(self):
        return [item.copy() for item in self._items]


class Order:
    def __init__(self):
        self._items = []

    def add_item(self, menu, name, quantity):
        try:
            quantity = int(quantity)
        except (TypeError, ValueError) as error:
            raise ValueError("จำนวนอาหารต้องเป็นจำนวนเต็ม") from error

        if quantity <= 0:
            raise ValueError("จำนวนอาหารต้องมากกว่า 0")

        selected_menu = next(
            (item for item in menu.get_menu_items() if item["name"] == name), None
        )
        if selected_menu is None:
            raise ValueError("ไม่พบเมนูที่เลือก")

        ordered_item = next(
            (item for item in self._items if item["name"] == name), None
        )
        if ordered_item:
            ordered_item["quantity"] += quantity
        else:
            self._items.append(
                {
                    "name": selected_menu["name"],
                    "price": selected_menu["price"],
                    "quantity": quantity,
                }
            )

    def get_items(self):
        return [item.copy() for item in self._items]

    def get_total(self):
        return sum(item["price"] * item["quantity"] for item in self._items)

    def clear(self):
        self._items.clear()


class RestaurantApp:
    def __init__(self):
        self._menu = Menu(Path(__file__).with_name("menu.json"))
        self._order = Order()
        self._html_path = Path(__file__).with_name("index.html")

    def __call__(self, environ, start_response):
        method = environ["REQUEST_METHOD"]
        path = environ.get("PATH_INFO", "/")

        try:
            if method == "GET" and path == "/":
                body = self._html_path.read_bytes()
                start_response(
                    "200 OK",
                    [
                        ("Content-Type", "text/html; charset=utf-8"),
                        ("Content-Length", str(len(body))),
                    ],
                )
                return [body]

            if method == "GET" and path == "/api/menu":
                return self._json_response(
                    start_response, "200 OK", self._menu.get_menu_items()
                )

            if method == "GET" and path == "/api/order":
                return self._json_response(
                    start_response, "200 OK", self._get_order_data()
                )

            if method == "POST" and path == "/api/menu":
                data = self._read_json(environ)
                self._menu.add_menu(data.get("name", ""), data.get("price"))
                return self._json_response(
                    start_response, "201 Created", self._menu.get_menu_items()
                )

            if method == "DELETE" and path == "/api/menu":
                data = self._read_json(environ)
                self._menu.remove_menu(data.get("name", ""))
                return self._json_response(
                    start_response, "200 OK", self._menu.get_menu_items()
                )

            if method == "POST" and path == "/api/order":
                data = self._read_json(environ)
                self._order.add_item(
                    self._menu, data.get("name", ""), data.get("quantity")
                )
                return self._json_response(
                    start_response, "200 OK", self._get_order_data()
                )

            if method == "DELETE" and path == "/api/order":
                self._order.clear()
                return self._json_response(
                    start_response, "200 OK", self._get_order_data()
                )

            return self._json_response(
                start_response, "404 Not Found", {"error": "ไม่พบหน้าที่เรียก"}
            )
        except ValueError as error:
            return self._json_response(
                start_response, "400 Bad Request", {"error": str(error)}
            )

    def _read_json(self, environ):
        length = int(environ.get("CONTENT_LENGTH") or 0)
        if length <= 0:
            raise ValueError("กรุณาส่งข้อมูลที่ต้องการบันทึก")
        try:
            return json.loads(environ["wsgi.input"].read(length))
        except json.JSONDecodeError as error:
            raise ValueError("ข้อมูลที่ส่งมาไม่ใช่ JSON ที่ถูกต้อง") from error

    def _get_order_data(self):
        return {"items": self._order.get_items(), "total": self._order.get_total()}

    def _json_response(self, start_response, status, data):
        body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        start_response(
            status,
            [
                ("Content-Type", "application/json; charset=utf-8"),
                ("Content-Length", str(len(body))),
            ],
        )
        return [body]

    def run(self):
        with make_server("127.0.0.1", 8000, self) as server:
            print("เปิดระบบได้ที่ http://127.0.0.1:8000")
            server.serve_forever()


if __name__ == "__main__":
    RestaurantApp().run()
