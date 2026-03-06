INDUSTRIES = [
    "Oil, Gas, and Petrochemicals",
    "Pharmaceuticals and APIs",
    "Electronics and Semiconductors",
    "Automotive and Auto Components",
    "Chemicals and Specialty Chemicals",
    "Fertilizers and Agri-inputs",
    "Food and Edible Oils",
    "Metals and Steel",
    "Textiles and Apparel",
    "Renewable Energy Equipment",
]


USER_ROLES = ["admin", "analyst", "viewer"]


EVENT_TYPE_WEIGHTS = {
    "tariff/policy": 1.2,
    "conflict/security": 1.35,
    "disaster/weather": 1.25,
    "logistics congestion": 1.15,
    "sanctions/compliance": 1.3,
    "operational incidents": 1.1,
    "other": 1.0,
}


DEFAULT_APPROVAL_STEPS = [
    "Supply Chain Head validates recommended scenario",
    "Procurement confirms supplier and contract feasibility",
    "Logistics team confirms lane and mode alternatives",
    "Finance signs off on cost and margin impact",
]


DEFAULT_OWNER_ASSIGNMENTS = {
    "procurement_owner": "Procurement Lead",
    "logistics_owner": "Logistics Control Tower",
    "risk_owner": "Risk and Compliance Manager",
    "finance_owner": "Finance Business Partner",
}
