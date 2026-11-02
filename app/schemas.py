from pydantic import BaseModel, Field


class TrackingInfo(BaseModel):
    carrier: str | None = Field(default=None, description="Carrier name or carrier slug")
    tracking_number: str | None = Field(default=None, description="Shipment tracking number")
    item_label: str | None = Field(default=None, description="Short human-readable item description")


class Shipment(BaseModel):
    id: int
    user_phone: str
    tracking_number: str
    carrier: str
    item_label: str
    status: str
    aftership_id: str | None
    created_at: str
    updated_at: str

