"""Integration (Gmail/LinkedIn account linking) routes - the Controller
layer for Phase 1 of `MULTI_AGENT_ROADMAP.md`.

Routes only translate HTTP <-> `IntegrationService`; no Composio SDK calls
or auth-config logic lives here - see
`app/services/integration_service.py`.
"""

from fastapi import APIRouter, HTTPException

from app.api.dependencies import IntegrationServiceDep
from app.api.schemas import ConnectResponse, IntegrationStatusOut

router = APIRouter(prefix="/api/integrations", tags=["integrations"])


@router.get("", response_model=list[IntegrationStatusOut])
async def list_integrations(service: IntegrationServiceDep):
    statuses = await service.list_statuses()
    return [
        IntegrationStatusOut(
            toolkit=s.toolkit,
            connected=s.connected,
            connected_since=s.connected_since,
            label=s.label,
        )
        for s in statuses
    ]


@router.post("/{toolkit}/connect", response_model=ConnectResponse)
async def connect_integration(toolkit: str, service: IntegrationServiceDep):
    try:
        redirect_url = await service.initiate_connection(toolkit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    return ConnectResponse(redirect_url=redirect_url)


@router.delete("/{toolkit}", status_code=204)
async def disconnect_integration(toolkit: str, service: IntegrationServiceDep):
    try:
        await service.disconnect(toolkit)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
