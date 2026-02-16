import React, { useEffect, useState } from 'react';

function ImageLightbox({ images, currentIndex, onClose, onNavigate }) {
    const [zoom, setZoom] = useState(1);
    const [position, setPosition] = useState({ x: 0, y: 0 });
    const [isDragging, setIsDragging] = useState(false);
    const [dragStart, setDragStart] = useState({ x: 0, y: 0 });

    useEffect(() => {
        // Reset zoom and position when image changes
        setZoom(1);
        setPosition({ x: 0, y: 0 });
    }, [currentIndex]);

    useEffect(() => {
        const handleKeyboard = (e) => {
            if (e.key === 'Escape') {
                onClose();
            } else if (e.key === 'ArrowLeft' && currentIndex > 0) {
                onNavigate(currentIndex - 1);
            } else if (e.key === 'ArrowRight' && currentIndex < images.length - 1) {
                onNavigate(currentIndex + 1);
            } else if (e.key === '+' || e.key === '=') {
                setZoom(z => Math.min(z + 0.25, 5));
            } else if (e.key === '-' || e.key === '_') {
                setZoom(z => Math.max(z - 0.25, 0.5));
            } else if (e.key === '0') {
                setZoom(1);
                setPosition({ x: 0, y: 0 });
            }
        };
        
        document.addEventListener('keydown', handleKeyboard);
        return () => document.removeEventListener('keydown', handleKeyboard);
    }, [onClose, currentIndex, images.length, onNavigate]);

    const handleMouseDown = (e) => {
        if (zoom > 1) {
            setIsDragging(true);
            setDragStart({ x: e.clientX - position.x, y: e.clientY - position.y });
        }
    };

    const handleMouseMove = (e) => {
        if (isDragging) {
            setPosition({
                x: e.clientX - dragStart.x,
                y: e.clientY - dragStart.y
            });
        }
    };

    const handleMouseUp = () => {
        setIsDragging(false);
    };

    const handleWheel = (e) => {
        e.preventDefault();
        const delta = e.deltaY > 0 ? -0.1 : 0.1;
        setZoom(z => Math.max(0.5, Math.min(5, z + delta)));
    };

    if (!images || images.length === 0) return null;

    const currentImage = images[currentIndex];
    const hasPrevious = currentIndex > 0;
    const hasNext = currentIndex < images.length - 1;

    return (
        <div 
            className="fixed inset-0 bg-black bg-opacity-95 z-[100] flex items-center justify-center"
            onClick={onClose}
        >
            {/* Close Button */}
            <button
                onClick={onClose}
                className="absolute top-4 right-4 p-2 rounded-full bg-black bg-opacity-50 hover:bg-opacity-70 transition text-white z-10"
                aria-label="Close lightbox"
            >
                <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
            </button>

            {/* Previous Button */}
            {hasPrevious && (
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        onNavigate(currentIndex - 1);
                    }}
                    className="absolute left-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-black bg-opacity-50 hover:bg-opacity-70 transition text-white z-10"
                    aria-label="Previous image"
                >
                    <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
                    </svg>
                </button>
            )}

            {/* Next Button */}
            {hasNext && (
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        onNavigate(currentIndex + 1);
                    }}
                    className="absolute right-4 top-1/2 -translate-y-1/2 p-3 rounded-full bg-black bg-opacity-50 hover:bg-opacity-70 transition text-white z-10"
                    aria-label="Next image"
                >
                    <svg className="h-8 w-8" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
                    </svg>
                </button>
            )}

            {/* Zoom Controls */}
            <div className="absolute bottom-4 left-1/2 -translate-x-1/2 flex items-center gap-2 bg-black bg-opacity-70 rounded-full px-4 py-2 z-10">
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        setZoom(z => Math.max(0.5, z - 0.25));
                    }}
                    className="p-2 rounded-full hover:bg-white hover:bg-opacity-20 transition text-white"
                    aria-label="Zoom out"
                >
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M20 12H4" />
                    </svg>
                </button>
                
                <span className="text-white font-medium min-w-[4rem] text-center text-sm">
                    {Math.round(zoom * 100)}%
                </span>
                
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        setZoom(z => Math.min(5, z + 0.25));
                    }}
                    className="p-2 rounded-full hover:bg-white hover:bg-opacity-20 transition text-white"
                    aria-label="Zoom in"
                >
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
                    </svg>
                </button>
                
                <div className="w-px h-6 bg-white bg-opacity-30 mx-1"></div>
                
                <button
                    onClick={(e) => {
                        e.stopPropagation();
                        setZoom(1);
                        setPosition({ x: 0, y: 0 });
                    }}
                    className="p-2 rounded-full hover:bg-white hover:bg-opacity-20 transition text-white"
                    aria-label="Reset zoom"
                    title="Reset zoom (0)"
                >
                    <svg className="h-5 w-5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                    </svg>
                </button>
            </div>

            {/* Image Counter */}
            {images.length > 1 && (
                <div className="absolute top-4 left-1/2 -translate-x-1/2 px-4 py-2 rounded-full bg-black bg-opacity-70 text-white font-medium z-10">
                    {currentIndex + 1} / {images.length}
                </div>
            )}
            
            {/* Image Container */}
            <div
                className="relative flex items-center justify-center"
                style={{
                    cursor: zoom > 1 ? (isDragging ? 'grabbing' : 'grab') : 'default',
                    width: '100%',
                    height: '100%',
                }}
                onMouseDown={handleMouseDown}
                onMouseMove={handleMouseMove}
                onMouseUp={handleMouseUp}
                onMouseLeave={handleMouseUp}
                onWheel={handleWheel}
                onClick={(e) => e.stopPropagation()}
            >
                <img
                    src={currentImage}
                    alt="Full size"
                    className="transition-transform"
                    style={{
                        maxWidth: zoom === 1 ? '100%' : 'none',
                        maxHeight: zoom === 1 ? '100%' : 'none',
                        width: zoom > 1 ? `${zoom * 100}%` : 'auto',
                        height: 'auto',
                        objectFit: 'contain',
                        transform: zoom > 1 ? `translate(${position.x}px, ${position.y}px)` : 'none',
                    }}
                    draggable={false}
                />
            </div>
        </div>
    );
}

export default ImageLightbox;
