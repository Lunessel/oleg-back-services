from typing import Annotated, Literal, Union

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, RootModel, StringConstraints

from app.services.phone import normalize_phone


def _valid_phone(value: str) -> str:
    phone = normalize_phone(value)
    if phone is None:
        raise ValueError("Вкажіть повний номер телефону")
    return phone


Phone = Annotated[str, AfterValidator(_valid_phone)]
Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=80)]
Address = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=200)]


class HeroLead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: Literal["hero"]
    from_: Address = Field(alias="from")
    to: Address
    phone: Phone


class CalculatorLead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    source: Literal["calculator"]
    name: Name
    phone: Phone
    serviceType: Literal["city", "intercity"]
    vanSize: Literal["small", "medium", "maxi"]
    loaders: Literal["none", "one", "two", "more"]
    # A service title from the bot's list, or free text when the user picked "Інше".
    service: Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=120)]
    serviceIsCustom: bool = False
    from_: Address = Field(alias="from")
    to: Address


class CallbackLead(BaseModel):
    source: Literal["callback"]
    name: Name
    phone: Phone


class ServicesConsultLead(BaseModel):
    source: Literal["services_consult"]
    name: Name
    phone: Phone


class LeadRequest(RootModel):
    root: Annotated[
        Union[HeroLead, CalculatorLead, CallbackLead, ServicesConsultLead],
        Field(discriminator="source"),
    ]


class ServiceOut(BaseModel):
    id: int
    title: str
    items: list[str]
    image: str


class PricingRowOut(BaseModel):
    label: str
    value: str


class PricingCardOut(BaseModel):
    id: str
    title: str
    rows: list[PricingRowOut]


class PricingOut(BaseModel):
    cards: list[PricingCardOut]
