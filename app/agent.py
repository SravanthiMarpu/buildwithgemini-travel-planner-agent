# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import base64
import datetime
import json
import os
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo

from pathlib import Path

from google import genai
from google.adk.agents import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.apps import App
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.cloud import storage
from google.genai import types

# Load Agent Engine resource name from deployment_metadata.json if present
metadata_file = Path(__file__).parent.parent / "deployment_metadata.json"
agent_engine_resource_name = None
if metadata_file.exists():
    try:
        with open(metadata_file) as f:
            metadata = json.load(f)
            agent_engine_resource_name = metadata.get("remote_agent_runtime_id")
    except Exception:
        pass


async def generate_memories_callback(callback_context: CallbackContext):
    try:
        await callback_context.add_session_to_memory()
    except ValueError:
        pass
    return None


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        city: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


def get_destination_info(destination: str) -> dict:
    """Gets travel information for a destination city including top attractions, best season to visit, and currency.

    Args:
        destination: The name of the destination city or country.

    Returns:
        A dictionary containing destination travel details.
    """
    dest_lower = destination.lower()
    if "tokyo" in dest_lower or "japan" in dest_lower:
        return {
            "destination": "Tokyo",
            "country": "Japan",
            "best_season": "Spring (March-May) & Autumn (Sept-Nov)",
            "top_attractions": ["Senso-ji Temple", "Shibuya Crossing", "Tokyo Skytree", "Meiji Shrine"],
            "currency": "JPY (¥)",
            "top_food": "Ramen, Sushi, Yakitori",
        }
    elif "paris" in dest_lower or "france" in dest_lower:
        return {
            "destination": "Paris",
            "country": "France",
            "best_season": "Spring (April-May) & Autumn (Sept-Oct)",
            "top_attractions": ["Eiffel Tower", "Louvre Museum", "Notre-Dame Cathedral", "Arc de Triomphe"],
            "currency": "EUR (€)",
            "top_food": "Croissant, Escargot, Baguette",
        }
    elif "sf" in dest_lower or "san francisco" in dest_lower:
        return {
            "destination": "San Francisco",
            "country": "United States",
            "best_season": "Autumn (September-November)",
            "top_attractions": ["Golden Gate Bridge", "Alcatraz Island", "Fisherman's Wharf", "Golden Gate Park"],
            "currency": "USD ($)",
            "top_food": "Clam Chowder in Sourdough, Dungeness Crab",
        }
    return {
        "destination": destination.title(),
        "best_season": "Spring & Autumn",
        "top_attractions": ["Historic City Center", "Main Plaza", "Local Cultural Museum"],
        "currency": "Local Currency",
        "top_food": "Local Culinary Specialties",
    }


def get_live_city_info(city: str) -> dict:
    """Fetches real-time geographical and current weather data for any city using public APIs.

    Args:
        city: The name of the city to query (e.g. "Paris", "Tokyo", "Rome").

    Returns:
        A dictionary with real location coordinates, country, timezone, population, elevation, and live weather.
    """
    api_key = os.getenv("OPENWEATHER_API_KEY")
    try:
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(city)}&count=1&language=en&format=json"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "travel-planner-agent"})
        with urllib.request.urlopen(req, timeout=5) as resp:
            geo_data = json.loads(resp.read().decode())

        if not geo_data.get("results"):
            return {"error": f"City '{city}' not found."}

        res = geo_data["results"][0]
        lat, lon = res["latitude"], res["longitude"]

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        req_w = urllib.request.Request(weather_url, headers={"User-Agent": "travel-planner-agent"})
        with urllib.request.urlopen(req_w, timeout=5) as resp_w:
            weather_data = json.loads(resp_w.read().decode())

        curr = weather_data.get("current_weather", {})
        return {
            "city": res.get("name"),
            "country": res.get("country"),
            "timezone": res.get("timezone"),
            "population": res.get("population"),
            "coordinates": {"latitude": lat, "longitude": lon},
            "elevation_meters": res.get("elevation"),
            "current_weather": {
                "temperature_celsius": curr.get("temperature"),
                "windspeed_kmh": curr.get("windspeed"),
                "weathercode": curr.get("weathercode"),
            },
        }
    except Exception as e:
        return {"error": f"Failed to fetch live data for {city}: {str(e)}"}


def geocode_address(address: str) -> dict:
    """Uses Google Maps Geocoding API to turn a physical address or landmark into geographic coordinates.

    Args:
        address: The address or landmark name (e.g., "1600 Amphitheatre Pkwy, Mountain View, CA" or "Eiffel Tower").

    Returns:
        A dictionary containing the formatted address and location coordinates (latitude, longitude).
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY is not configured in environment."}

    try:
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={urllib.parse.quote(address)}&key={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return {"error": f"Geocoding failed for '{address}': {data.get('status', 'NO_RESULTS')}"}

        first_result = data["results"][0]
        location = first_result["geometry"]["location"]
        return {
            "address": address,
            "formatted_address": first_result.get("formatted_address"),
            "location": {
                "latitude": location.get("lat"),
                "longitude": location.get("lng"),
            },
        }
    except Exception as e:
        return {"error": f"Geocoding API error: {str(e)}"}


def search_nearby_places(query_or_type: str, latitude: float, longitude: float, radius_meters: float = 1000.0) -> dict:
    """Uses Google Places API (New) to search for nearby places (restaurants, hotels, attractions, etc.) around coordinates.

    Args:
        query_or_type: The place type (e.g., "restaurant", "tourist_attraction", "lodging", "cafe", "museum").
        latitude: Center latitude coordinate.
        longitude: Center longitude coordinate.
        radius_meters: Search radius in meters (default 1000.0).

    Returns:
        A dictionary with a list of nearby places containing name, formatted address, location, and rating.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return {"error": "GOOGLE_MAPS_API_KEY is not configured in environment."}

    url = "https://places.googleapis.com/v1/places:searchNearby"
    headers = {
        "Content-Type": "application/json",
        "X-Goog-Api-Key": api_key,
        "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.rating,places.types",
    }
    body = {
        "includedTypes": [query_or_type.lower().strip()],
        "maxResultCount": 10,
        "locationRestriction": {
            "circle": {
                "center": {
                    "latitude": float(latitude),
                    "longitude": float(longitude),
                },
                "radius": float(radius_meters),
            }
        },
    }

    try:
        req = urllib.request.Request(url, data=json.dumps(body).encode(), headers=headers, method="POST")
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())

        places = []
        for p in data.get("places", []):
            places.append({
                "name": p.get("displayName", {}).get("text"),
                "address": p.get("formattedAddress"),
                "location": {
                    "latitude": p.get("location", {}).get("latitude"),
                    "longitude": p.get("location", {}).get("longitude"),
                },
                "rating": p.get("rating"),
                "types": p.get("types"),
            })

        return {
            "query_type": query_or_type,
            "center": {"latitude": latitude, "longitude": longitude},
            "radius_meters": radius_meters,
            "places_count": len(places),
            "places": places,
        }
    except Exception as e:
        return {"error": f"Places API (New) error: {str(e)}"}


async def generate_destination_image(description: str, tool_context: ToolContext) -> dict:
    """Generates an image for a travel destination or landmark using gemini-3.1-flash-lite-image in the global region,
    saves it as an artifact in the session context, and uploads it to public Cloud Storage.

    Args:
        description: Visual description of the destination image to generate (e.g., "Postcard illustration of Mt Fuji with cherry blossoms").

    Returns:
        A dictionary containing the generated image filename, public storage URL, and status.
    """
    try:
        client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-02-0420cd5f6f8a"),
            location="global",
        )
        prompt = f"A beautiful travel photograph or postcard of: {description}"
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        if not response.candidates or not response.candidates[0].content.parts:
            return {"error": "No image generated by gemini-3.1-flash-lite-image."}

        part = response.candidates[0].content.parts[0]
        if not hasattr(part, "inline_data") or not part.inline_data:
            return {"error": "Model response did not contain inline image data."}

        image_bytes = part.inline_data.data
        mime_type = part.inline_data.mime_type or "image/jpeg"
        ext = "png" if "png" in mime_type else "jpg"

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"destination_{timestamp}.{ext}"

        # (1) Save artifact via tool_context
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload to public Cloud Storage bucket (hardcoded string)
        bucket_name = "travel-planner-media-qwiklabs-gcp-02-0420cd5f6f8a"
        gcs_client = storage.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-02-0420cd5f6f8a"))
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{bucket_name}/{filename}"

        return {
            "status": "success",
            "filename": filename,
            "public_url": public_url,
            "description": description,
        }
    except Exception as e:
        return {"error": f"Image generation error: {str(e)}"}


async def generate_destination_video(description: str, tool_context: ToolContext) -> dict:
    """Generates a short video for a travel destination or landmark using Google's Omni model (gemini-omni-flash-preview) in the global region,
    saves it as an artifact in the session context, and uploads it to public Cloud Storage.

    Args:
        description: Visual description of the destination video to generate (e.g. "Scenic 3-second video of tropical ocean waves at a beach resort").

    Returns:
        A dictionary containing the generated video filename, public storage URL, and status.
    """
    try:
        client = genai.Client(
            vertexai=True,
            project=os.getenv("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-02-0420cd5f6f8a"),
            location="global",
        )
        prompt = f"A short video of: {description}"
        interaction = client.interactions.create(
            model="gemini-omni-flash-preview",
            input=prompt,
        )

        video_bytes = None
        mime_type = "video/mp4"

        if hasattr(interaction, "output_video") and interaction.output_video and hasattr(interaction.output_video, "data") and interaction.output_video.data:
            val = interaction.output_video.data
            if isinstance(val, str):
                video_bytes = base64.b64decode(val)
            elif isinstance(val, bytes):
                video_bytes = val
        elif hasattr(interaction, "steps") and interaction.steps:
            for step in interaction.steps:
                step_dict = step.model_dump() if hasattr(step, "model_dump") else (step if isinstance(step, dict) else {})
                if step_dict.get("type") == "model_output":
                    for c in step_dict.get("content", []):
                        if c.get("type") == "video" and "data" in c:
                            video_bytes = base64.b64decode(c["data"]) if isinstance(c["data"], str) else c["data"]
                            mime_type = c.get("mime_type", "video/mp4")
                            break

        if not video_bytes:
            return {"error": "No video data returned from gemini-omni-flash-preview."}

        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"destination_video_{timestamp}.mp4"

        # (1) Save artifact via tool_context
        artifact_part = types.Part.from_bytes(data=video_bytes, mime_type=mime_type)
        await tool_context.save_artifact(filename=filename, artifact=artifact_part)

        # (2) Upload to public Cloud Storage bucket (hardcoded string)
        bucket_name = "travel-planner-media-qwiklabs-gcp-02-0420cd5f6f8a"
        gcs_client = storage.Client(project=os.getenv("GOOGLE_CLOUD_PROJECT", "qwiklabs-gcp-02-0420cd5f6f8a"))
        bucket = gcs_client.bucket(bucket_name)
        blob = bucket.blob(filename)
        blob.upload_from_string(video_bytes, content_type=mime_type)

        public_url = f"https://storage.googleapis.com/{bucket_name}/{filename}"

        return {
            "status": "success",
            "filename": filename,
            "public_url": public_url,
            "description": description,
        }
    except Exception as e:
        return {"error": f"Video generation error: {str(e)}"}


from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager

from .a2ui_utils import a2ui_callback

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are a helpful AI travel concierge assistant designed to provide travel insights, "
        "weather info, destination details, geocoding, nearby places search, destination image generation, "
        "destination video generation, and Python code execution. Always remember and track all user allergies (such as food allergies, "
        "medical allergies, dietary restrictions, and health conditions) and personal preferences from "
        "previous conversations, and strictly tailor all travel plans, food recommendations, and advice to respect these allergies."
    ),
    workflow_description="Analyze the request and return structured UI when appropriate.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    code_executor=AgentEngineSandboxCodeExecutor(
        agent_engine_resource_name=agent_engine_resource_name
    ) if agent_engine_resource_name else None,
    tools=[
        PreloadMemoryTool(),
        get_weather,
        get_current_time,
        get_destination_info,
        get_live_city_info,
        geocode_address,
        search_nearby_places,
        generate_destination_image,
        generate_destination_video,
    ],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
