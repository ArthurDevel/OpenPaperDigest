import { NextRequest, NextResponse } from 'next/server';

/**
 * Health check endpoint for Railway deployment.
 * 
 * This endpoint is accessible directly at /health on the frontend port (3000).
 * It proxies to the backend /health endpoint to verify both services are running.
 * 
 * Railway will check this endpoint to determine if the application is ready.
 * 
 * @returns 200 OK if both frontend and backend are healthy
 * @returns 503 Service Unavailable if backend is not responding
 */
const BACKEND_URL = `http://127.0.0.1:${process.env.NEXT_PUBLIC_CONTAINERPORT_API || 8000}`;

export async function GET(req: NextRequest) {
    try {
        // Proxy to backend health endpoint
        const backendResponse = await fetch(`${BACKEND_URL}/health`, {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json',
            },
        });

        if (!backendResponse.ok) {
            return NextResponse.json(
                { status: 'unhealthy', error: 'Backend health check failed' },
                { status: 503 }
            );
        }

        const backendData = await backendResponse.json();
        
        // Return combined health status
        return NextResponse.json({
            status: 'healthy',
            frontend: 'ready',
            backend: backendData.status || 'ready',
        });
    } catch (error) {
        // Backend is not responding
        return NextResponse.json(
            { status: 'unhealthy', error: 'Backend not available' },
            { status: 503 }
        );
    }
}
