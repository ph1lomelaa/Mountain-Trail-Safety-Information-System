from typing import Optional

from pydantic import BaseModel


class TrailOut(BaseModel):
    id: int
    name: str
    description: Optional[str]
    difficulty: str
    length_km: float
    elevation_gain_m: float
    start_lat: float
    start_lng: float
    end_lat: float
    end_lng: float
    h3_index: str
    h3_resolution: int
    geometry_json: Optional[str] = None
    source: Optional[str] = None
    source_id: Optional[str] = None
    created_at: str


class POIOut(BaseModel):
    id: int
    name: str
    category: str
    description: Optional[str]
    latitude: float
    longitude: float
    h3_index: str
    trail_id: Optional[int]
    source: Optional[str] = None
    source_id: Optional[str] = None


class SafetyCheckinCreate(BaseModel):
    trail_id: int
    expected_return: str
    emergency_contact: Optional[str] = None
    phone_number: Optional[str] = None
    group_size: int = 1
    notes: Optional[str] = None
    latitude: float
    longitude: float


class SafetyCheckinOut(BaseModel):
    id: int
    user_id: int
    trail_id: int
    status: str
    expected_return: str
    emergency_contact: Optional[str]
    phone_number: Optional[str]
    group_size: int
    h3_index: str
    checked_in_at: str
    checked_out_at: Optional[str]
