"""
TestPilot Project Routes — Cleaned
====================================
"""

from __future__ import annotations
import logging
from bson import ObjectId
from bson.errors import InvalidId
from fastapi import APIRouter, HTTPException, Query

from app.database import projects_collection, chat_sessions_collection, chat_messages_collection, generated_tests_collection
from app.schemas.project import (
    CreateProjectRequest, UpdateProjectRequest,
    ProjectSummaryResponse, ProjectDetailResponse,
    ProjectListResponse, ProjectCreatedResponse, ProjectDeletedResponse,
)
from app.models.project import ProjectDocument

logger = logging.getLogger("testpilot.routes.projects")
router = APIRouter()


def _oid(id_str: str) -> ObjectId:
    try:
        return ObjectId(id_str)
    except (InvalidId, TypeError):
        raise HTTPException(400, f"Invalid ID: {id_str}")


@router.post("", response_model=ProjectCreatedResponse, status_code=201)
async def create_project(request: CreateProjectRequest):
    col = projects_collection()
    existing = await col.find_one({"name": request.name})
    if existing:
        raise HTTPException(409, f"Project '{request.name}' already exists")

    project = ProjectDocument(
        name=request.name,
        description=request.description,
        base_url=request.base_url,
        tags=request.tags,
    )
    result = await col.insert_one(project.to_mongo())
    return ProjectCreatedResponse(
        id=str(result.inserted_id),
        name=request.name,
        base_url=request.base_url,
    )


@router.get("", response_model=ProjectListResponse)
async def list_projects(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: str = Query(None),
):
    col = projects_collection()
    query = {}
    if search:
        query["$or"] = [
            {"name": {"$regex": search, "$options": "i"}},
            {"base_url": {"$regex": search, "$options": "i"}},
        ]

    total = await col.count_documents(query)
    skip = (page - 1) * limit
    cursor = col.find(query).sort("updated_at", -1).skip(skip).limit(limit)

    items = [ProjectSummaryResponse.from_mongo(doc) async for doc in cursor]
    return ProjectListResponse.create(items=items, total=total, page=page, limit=limit)


@router.get("/{project_id}", response_model=ProjectDetailResponse)
async def get_project(project_id: str):
    doc = await projects_collection().find_one({"_id": _oid(project_id)})
    if not doc:
        raise HTTPException(404, "Project not found")
    return ProjectDetailResponse.from_mongo(doc)


@router.put("/{project_id}", response_model=ProjectDetailResponse)
async def update_project(project_id: str, request: UpdateProjectRequest):
    oid = _oid(project_id)
    col = projects_collection()
    doc = await col.find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Project not found")

    if request.name and request.name != doc.get("name"):
        existing = await col.find_one({"name": request.name, "_id": {"$ne": oid}})
        if existing:
            raise HTTPException(409, f"Project '{request.name}' already exists")

    update_data = request.to_update_dict()
    if not update_data:
        raise HTTPException(400, "No fields to update")

    await col.update_one({"_id": oid}, {"$set": update_data})
    updated = await col.find_one({"_id": oid})
    return ProjectDetailResponse.from_mongo(updated)


@router.delete("/{project_id}", response_model=ProjectDeletedResponse)
async def delete_project(project_id: str):
    oid = _oid(project_id)
    doc = await projects_collection().find_one({"_id": oid})
    if not doc:
        raise HTTPException(404, "Project not found")

    # Delete all related data
    sessions = chat_sessions_collection()
    messages = chat_messages_collection()
    tests = generated_tests_collection()

    session_cursor = sessions.find({"project_id": project_id}, {"_id": 1})
    session_ids = [str(s["_id"]) async for s in session_cursor]

    if session_ids:
        await messages.delete_many({"session_id": {"$in": session_ids}})
        await tests.delete_many({"session_id": {"$in": session_ids}})
        await sessions.delete_many({"project_id": project_id})

    await projects_collection().delete_one({"_id": oid})
    return ProjectDeletedResponse(id=project_id)