from sqlmodel import SQLModel, Field, Relationship
from datetime import datetime
from decimal import Decimal
from typing import Optional, List, Dict, Any
from enum import Enum
import string
import secrets


class UserRole(str, Enum):
    ADMIN = "Admin"
    KASIR = "Kasir"


class UnitType(str, Enum):
    ECER = "Ecer"
    GROSIR = "Grosir"


class TransactionStatus(str, Enum):
    PENDING = "Pending"
    COMPLETED = "Completed"
    CANCELLED = "Cancelled"


# Persistent models (stored in database)
class User(SQLModel, table=True):
    __tablename__ = "users"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(max_length=50, unique=True, index=True)
    password_hash: str = Field(max_length=255)  # Store hashed passwords
    full_name: str = Field(max_length=100)
    role: UserRole = Field(default=UserRole.KASIR)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    transactions: List["Transaction"] = Relationship(back_populates="user")


class Category(SQLModel, table=True):
    __tablename__ = "categories"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(max_length=100, unique=True, index=True)
    description: str = Field(default="", max_length=500)
    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    items: List["Item"] = Relationship(back_populates="category")


class Item(SQLModel, table=True):
    __tablename__ = "items"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    barcode: str = Field(max_length=20, unique=True, index=True)
    name: str = Field(max_length=200, unique=True, index=True)
    category_id: int = Field(foreign_key="categories.id")

    # Wholesale (Grosir) pricing and units
    wholesale_cost_price: Decimal = Field(default=Decimal("0"), decimal_places=2)
    wholesale_selling_price: Decimal = Field(default=Decimal("0"), decimal_places=2)
    quantity_per_wholesale: int = Field(default=1, gt=0)  # How many Ecer units in 1 Grosir

    # Retail (Ecer) pricing - base unit
    retail_cost_price: Decimal = Field(default=Decimal("0"), decimal_places=2)
    retail_selling_price: Decimal = Field(default=Decimal("0"), decimal_places=2)

    # Stock is always managed in smallest unit (Ecer)
    stock_quantity: int = Field(default=0, ge=0)
    minimum_stock: int = Field(default=0, ge=0)

    is_active: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    category: Category = Relationship(back_populates="items")
    transaction_items: List["TransactionItem"] = Relationship(back_populates="item")

    def generate_barcode(self) -> str:
        """Generate a 10-character alphanumeric uppercase barcode"""
        characters = string.ascii_uppercase + string.digits
        return "".join(secrets.choice(characters) for _ in range(10))

    def get_price_by_unit(self, unit_type: UnitType) -> Decimal:
        """Get selling price based on unit type"""
        if unit_type == UnitType.GROSIR:
            return self.wholesale_selling_price
        return self.retail_selling_price

    def convert_to_ecer_quantity(self, quantity: int, unit_type: UnitType) -> int:
        """Convert quantity to Ecer (base unit) for stock management"""
        if unit_type == UnitType.GROSIR:
            return quantity * self.quantity_per_wholesale
        return quantity

    def can_fulfill_order(self, quantity: int, unit_type: UnitType) -> bool:
        """Check if there's enough stock for the order"""
        required_ecer_quantity = self.convert_to_ecer_quantity(quantity, unit_type)
        return self.stock_quantity >= required_ecer_quantity


class Transaction(SQLModel, table=True):
    __tablename__ = "transactions"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_number: str = Field(max_length=50, unique=True, index=True)
    user_id: int = Field(foreign_key="users.id")

    subtotal: Decimal = Field(default=Decimal("0"), decimal_places=2)
    tax_amount: Decimal = Field(default=Decimal("0"), decimal_places=2)
    discount_amount: Decimal = Field(default=Decimal("0"), decimal_places=2)
    total_amount: Decimal = Field(default=Decimal("0"), decimal_places=2)

    payment_amount: Decimal = Field(default=Decimal("0"), decimal_places=2)
    change_amount: Decimal = Field(default=Decimal("0"), decimal_places=2)

    status: TransactionStatus = Field(default=TransactionStatus.PENDING)
    notes: str = Field(default="", max_length=500)

    transaction_date: datetime = Field(default_factory=datetime.utcnow)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    user: User = Relationship(back_populates="transactions")
    transaction_items: List["TransactionItem"] = Relationship(back_populates="transaction")

    def generate_transaction_number(self) -> str:
        """Generate a unique transaction number"""
        timestamp = datetime.utcnow().strftime("%Y%m%d%H%M%S")
        random_suffix = "".join(secrets.choice(string.digits) for _ in range(4))
        return f"TXN{timestamp}{random_suffix}"

    def calculate_totals(self) -> None:
        """Calculate subtotal and total from transaction items"""
        self.subtotal = sum((item.total_price for item in self.transaction_items), Decimal("0"))
        self.total_amount = self.subtotal + self.tax_amount - self.discount_amount
        self.change_amount = max(Decimal("0"), self.payment_amount - self.total_amount)


class TransactionItem(SQLModel, table=True):
    __tablename__ = "transaction_items"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    transaction_id: int = Field(foreign_key="transactions.id")
    item_id: int = Field(foreign_key="items.id")

    quantity: int = Field(gt=0)
    unit_type: UnitType = Field(default=UnitType.ECER)
    unit_price: Decimal = Field(decimal_places=2)  # Price per unit at time of sale
    total_price: Decimal = Field(decimal_places=2)  # quantity * unit_price

    # Store the quantity in Ecer units for stock management
    ecer_quantity: int = Field(gt=0)  # Converted quantity in base units

    created_at: datetime = Field(default_factory=datetime.utcnow)

    # Relationships
    transaction: Transaction = Relationship(back_populates="transaction_items")
    item: Item = Relationship(back_populates="transaction_items")

    def calculate_totals(self, item: Item) -> None:
        """Calculate total price and ecer quantity"""
        self.unit_price = item.get_price_by_unit(self.unit_type)
        self.total_price = Decimal(str(self.quantity)) * self.unit_price
        self.ecer_quantity = item.convert_to_ecer_quantity(self.quantity, self.unit_type)


# Stock movement tracking
class StockMovement(SQLModel, table=True):
    __tablename__ = "stock_movements"  # type: ignore[assignment]

    id: Optional[int] = Field(default=None, primary_key=True)
    item_id: int = Field(foreign_key="items.id")
    transaction_item_id: Optional[int] = Field(foreign_key="transaction_items.id", default=None)

    movement_type: str = Field(max_length=20)  # 'SALE', 'ADJUSTMENT', 'RESTOCK'
    quantity_change: int = Field()  # Positive for additions, negative for sales
    previous_stock: int = Field(ge=0)
    new_stock: int = Field(ge=0)

    reason: str = Field(default="", max_length=200)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    created_by: int = Field(foreign_key="users.id")


# Non-persistent schemas (for validation, forms, API requests/responses)
class UserCreate(SQLModel, table=False):
    username: str = Field(max_length=50)
    password: str = Field(min_length=6, max_length=100)
    full_name: str = Field(max_length=100)
    role: UserRole = Field(default=UserRole.KASIR)


class UserUpdate(SQLModel, table=False):
    username: Optional[str] = Field(default=None, max_length=50)
    full_name: Optional[str] = Field(default=None, max_length=100)
    role: Optional[UserRole] = Field(default=None)
    is_active: Optional[bool] = Field(default=None)


class CategoryCreate(SQLModel, table=False):
    name: str = Field(max_length=100)
    description: str = Field(default="", max_length=500)


class CategoryUpdate(SQLModel, table=False):
    name: Optional[str] = Field(default=None, max_length=100)
    description: Optional[str] = Field(default=None, max_length=500)
    is_active: Optional[bool] = Field(default=None)


class ItemCreate(SQLModel, table=False):
    barcode: Optional[str] = Field(default=None, max_length=20)  # Auto-generated if None
    name: str = Field(max_length=200)
    category_id: int
    wholesale_cost_price: Decimal = Field(default=Decimal("0"), decimal_places=2)
    wholesale_selling_price: Decimal = Field(default=Decimal("0"), decimal_places=2)
    quantity_per_wholesale: int = Field(default=1, gt=0)
    retail_cost_price: Decimal = Field(default=Decimal("0"), decimal_places=2)
    retail_selling_price: Decimal = Field(default=Decimal("0"), decimal_places=2)
    stock_quantity: int = Field(default=0, ge=0)
    minimum_stock: int = Field(default=0, ge=0)


class ItemUpdate(SQLModel, table=False):
    name: Optional[str] = Field(default=None, max_length=200)
    category_id: Optional[int] = Field(default=None)
    wholesale_cost_price: Optional[Decimal] = Field(default=None, decimal_places=2)
    wholesale_selling_price: Optional[Decimal] = Field(default=None, decimal_places=2)
    quantity_per_wholesale: Optional[int] = Field(default=None, gt=0)
    retail_cost_price: Optional[Decimal] = Field(default=None, decimal_places=2)
    retail_selling_price: Optional[Decimal] = Field(default=None, decimal_places=2)
    stock_quantity: Optional[int] = Field(default=None, ge=0)
    minimum_stock: Optional[int] = Field(default=None, ge=0)
    is_active: Optional[bool] = Field(default=None)


class TransactionCreate(SQLModel, table=False):
    items: List[Dict[str, Any]] = Field(default=[])  # List of {item_id, quantity, unit_type}
    tax_amount: Decimal = Field(default=Decimal("0"), decimal_places=2)
    discount_amount: Decimal = Field(default=Decimal("0"), decimal_places=2)
    payment_amount: Decimal = Field(decimal_places=2)
    notes: str = Field(default="", max_length=500)


class TransactionItemCreate(SQLModel, table=False):
    item_id: int
    quantity: int = Field(gt=0)
    unit_type: UnitType = Field(default=UnitType.ECER)


class StockAdjustment(SQLModel, table=False):
    item_id: int
    new_quantity: int = Field(ge=0)
    reason: str = Field(max_length=200)


# Response schemas for API
class ItemResponse(SQLModel, table=False):
    id: int
    barcode: str
    name: str
    category_id: int
    category_name: str
    wholesale_cost_price: Decimal
    wholesale_selling_price: Decimal
    quantity_per_wholesale: int
    retail_cost_price: Decimal
    retail_selling_price: Decimal
    stock_quantity: int
    minimum_stock: int
    is_active: bool
    is_low_stock: bool
    created_at: str  # ISO format string
    updated_at: str  # ISO format string


class TransactionResponse(SQLModel, table=False):
    id: int
    transaction_number: str
    user_id: int
    user_name: str
    subtotal: Decimal
    tax_amount: Decimal
    discount_amount: Decimal
    total_amount: Decimal
    payment_amount: Decimal
    change_amount: Decimal
    status: TransactionStatus
    notes: str
    transaction_date: str  # ISO format string
    items: List[Dict[str, Any]]
