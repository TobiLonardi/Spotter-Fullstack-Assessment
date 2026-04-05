import { useEffect } from 'react'
import { MapContainer, Marker, Polyline, Popup, TileLayer, useMap } from 'react-leaflet'
import 'leaflet/dist/leaflet.css'
import './leafletSetup.js'

function FitBounds({ positions }) {
  const map = useMap()
  useEffect(() => {
    if (positions.length === 0) return
    if (positions.length === 1) {
      map.setView(positions[0], 10)
      return
    }
    const latLngs = positions.map(([lat, lng]) => [lat, lng])
    map.fitBounds(latLngs, { padding: [48, 48] })
  }, [map, positions])
  return null
}

export default function TripMap({ lineLatLng, stops }) {
  const positions = lineLatLng?.length ? lineLatLng : (stops || []).map((s) => [s.lat, s.lng])
  // Rough US center when we have nothing yet (e.g. first paint before fitBounds).
  const center = positions[0] || [39.8283, -98.5795]

  return (
    <div className="map-wrap">
      <MapContainer
        center={center}
        zoom={5}
        scrollWheelZoom
        className="trip-map"
      >
        <TileLayer
          attribution='&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>'
          url="https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png"
        />
        <FitBounds positions={positions} />
        {lineLatLng?.length > 1 && (
          <Polyline positions={lineLatLng} color="#1e5a8c" weight={5} opacity={0.85} />
        )}
        {(stops || []).map((s) => (
          <Marker key={s.id} position={[s.lat, s.lng]}>
            <Popup>{s.label}</Popup>
          </Marker>
        ))}
      </MapContainer>
    </div>
  )
}
