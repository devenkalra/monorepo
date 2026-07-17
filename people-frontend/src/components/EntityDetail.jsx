import React, { useState, useEffect, useRef, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import ImageLightbox from './ImageLightbox';
import RichTextEditor from './RichTextEditor';
import TagInput from './TagInput';
import api from '../services/api';
import { getMediaUrl } from '../utils/apiUrl';
import { useEncryption } from '../contexts/EncryptionContext';

const generateUUID = () => {
    if (typeof self !== 'undefined' && self.crypto && typeof self.crypto.randomUUID === 'function') {
        return self.crypto.randomUUID();
    }
    return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, function(c) {
        var r = Math.random() * 16 | 0, v = c === 'x' ? r : (r & 0x3 | 0x8);
        return v.toString(16);
    });
};

function DecryptedImage({ src, alt, className, onClick, title, decryptionKey }) {
    const { decryptBlob } = useEncryption();
    const [decryptedSrc, setDecryptedSrc] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        if (!src) return;
        
        let active = true;
        const loadAndDecrypt = async () => {
            try {
                setLoading(true);
                const response = await fetch(src);
                if (!response.ok) throw new Error('Failed to fetch media');
                const encryptedBlob = await response.blob();
                
                let mimeType = 'image/jpeg';
                if (src.toLowerCase().includes('.png')) mimeType = 'image/png';
                if (src.toLowerCase().includes('.gif')) mimeType = 'image/gif';
                if (src.toLowerCase().includes('.webp')) mimeType = 'image/webp';
                
                const decryptedBlob = await decryptBlob(encryptedBlob, mimeType, decryptionKey);
                
                if (active) {
                    const objectUrl = URL.createObjectURL(decryptedBlob);
                    setDecryptedSrc(objectUrl);
                }
            } catch (err) {
                console.error('Failed to decrypt image:', err);
            } finally {
                if (active) setLoading(false);
            }
        };

        loadAndDecrypt();

        return () => {
            active = false;
            if (decryptedSrc) {
                URL.revokeObjectURL(decryptedSrc);
            }
        };
    }, [src, decryptionKey]);

    if (loading) {
        return (
            <div className={`flex items-center justify-center bg-gray-100 dark:bg-gray-800 animate-pulse ${className}`}>
                <svg className="w-6 h-6 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16l4.586-4.586a2 2 0 012.828 0L16 16m-2-2l1.586-1.586a2 2 0 012.828 0L20 14m-6-6h.01M6 20h12a2 2 0 002-2V6a2 2 0 00-2-2H6a2 2 0 00-2 2v12a2 2 0 002 2z" />
                </svg>
            </div>
        );
    }

    return (
        <img
            src={decryptedSrc || src}
            alt={alt}
            className={className}
            onClick={onClick}
            title={title}
        />
    );
}

function EntityDetail({ entity, onClose, isVisible, onUpdate, onCreate, initialViewMode }) {
    const navigate = useNavigate();
    const { hasKeys, encryptionKeys, deriveKey, encryptText, decryptText, encryptBlob, decryptBlob } = useEncryption();
    const [decryptedEntity, setDecryptedEntity] = useState(null);
    const [vaultPassphrase, setVaultPassphrase] = useState('');
    const [isInitializingKey, setIsInitializingKey] = useState(false);

    const handleAttachmentClick = async (url, filename, decryptionKey) => {
        try {
            const fullUrl = getMediaUrl(url);
            const response = await fetch(fullUrl);
            if (!response.ok) throw new Error('Failed to fetch encrypted attachment');
            const encryptedBlob = await response.blob();
            
            let mimeType = 'application/octet-stream';
            const cleanFilename = filename.endsWith('.enc') ? filename.slice(0, -4) : filename;
            
            const decryptedBlob = await decryptBlob(encryptedBlob, mimeType, decryptionKey);
            
            const blobUrl = URL.createObjectURL(decryptedBlob);
            const a = document.createElement('a');
            a.href = blobUrl;
            a.download = cleanFilename;
            document.body.appendChild(a);
            a.click();
            URL.revokeObjectURL(blobUrl);
            document.body.removeChild(a);
        } catch (err) {
            console.error('Failed to decrypt attachment:', err);
            alert('Failed to decrypt attachment. Is the vault unlocked?');
        }
    };

    const [isAnimating, setIsAnimating] = useState(false);
    const [shouldRender, setShouldRender] = useState(false);
    const displayEntityRef = useRef(null);
    const descriptionRef = useRef(null);
    const [isEditing, setIsEditing] = useState(false);
    const [editedEntity, setEditedEntity] = useState(null);
    const displayEntity = isEditing ? editedEntity : decryptedEntity;
    const [processedDescription, setProcessedDescription] = useState('');
    const descriptionBlobUrlsRef = useRef([]);
    const [isSaving, setIsSaving] = useState(false);
    const [newPhotos, setNewPhotos] = useState([]);
    const [newAttachments, setNewAttachments] = useState([]);
    const [deletedPhotos, setDeletedPhotos] = useState([]);
    const [deletedAttachments, setDeletedAttachments] = useState([]);
    const [lightboxImages, setLightboxImages] = useState([]);
    const [lightboxIndex, setLightboxIndex] = useState(0);
    const [viewMode, setViewMode] = useState('details'); // 'details', 'edit', or 'relations'
    const [relations, setRelations] = useState({ outgoing: [], incoming: [] });
    const [isLoadingRelations, setIsLoadingRelations] = useState(false);
    const [isAddingRelation, setIsAddingRelation] = useState(false);
    const [newRelation, setNewRelation] = useState({ targetEntity: '', relationType: '', targetEntityData: null });
    const [entitySearchResults, setEntitySearchResults] = useState([]);
    const [entitySearchQuery, setEntitySearchQuery] = useState('');
    const [availableRelationTypes, setAvailableRelationTypes] = useState([]);
    const [relationsFilter, setRelationsFilter] = useState('');
    const [expandedRelations, setExpandedRelations] = useState({});
    const [geocodeLoading, setGeocodeLoading] = useState(null); // { idx, type: 'forward'|'reverse' }
    const [isDraggingPhotos, setIsDraggingPhotos] = useState(false);
    const [isDraggingAttachments, setIsDraggingAttachments] = useState(false);

    useEffect(() => {
        if (entity && isVisible) {
            // Ensure urls, photos, attachments, and locations are arrays
            const normalizedEntity = {
                ...entity,
                urls: Array.isArray(entity.urls) ? entity.urls : (entity.urls ? [] : []),
                photos: Array.isArray(entity.photos) ? entity.photos : (entity.photos ? [] : []),
                attachments: Array.isArray(entity.attachments) ? entity.attachments : (entity.attachments ? [] : []),
                locations: Array.isArray(entity.locations) ? entity.locations : (entity.locations ? [] : [])
            };

            // Handle initial view mode
            // initialViewMode can be: 'details', 'relations', 'edit', 'relations-edit'
            if (initialViewMode === 'edit') {
                // Edit mode on details tab
                setIsEditing(true);
                setViewMode('details');
            } else if (initialViewMode === 'relations-edit') {
                // Edit mode on relations tab
                setIsEditing(true);
                setViewMode('relations');
            } else if (entity.isNew === true) {
                // New entity - start in edit mode
                setIsEditing(true);
                setViewMode('details');
            } else {
                // Normal mode - set view mode and clear editing
                setIsEditing(false);
                setViewMode(initialViewMode || 'details');
            }

            setNewPhotos([]);
            setNewAttachments([]);
            setDeletedPhotos([]);
            setDeletedAttachments([]);
            // Entity selected - mount and animate in
            setShouldRender(true);
            // Delay to ensure initial render before animation
            requestAnimationFrame(() => {
                requestAnimationFrame(() => {
                    setIsAnimating(true);
                });
            });
        } else if (!entity || !isVisible) {
            // Entity deselected - animate out then unmount
            setIsAnimating(false);
            const timer = setTimeout(() => {
                setShouldRender(false);
                displayEntityRef.current = null;
                setEditedEntity(null);
                setDecryptedEntity(null);
                setIsEditing(false);
                setViewMode('details');
            }, 300);
            return () => clearTimeout(timer);
        }
    }, [entity, isVisible, initialViewMode]);

    useEffect(() => {
        if (!entity || !isVisible) {
            setDecryptedEntity(null);
            return;
        }

        let active = true;

        const decrypt = async () => {
            const normalizedEntity = {
                ...entity,
                urls: Array.isArray(entity.urls) ? entity.urls : [],
                photos: Array.isArray(entity.photos) ? entity.photos : [],
                attachments: Array.isArray(entity.attachments) ? entity.attachments : [],
                locations: Array.isArray(entity.locations) ? entity.locations : []
            };

            if (!normalizedEntity.is_encrypted) {
                if (active) {
                    setDecryptedEntity(normalizedEntity);
                    displayEntityRef.current = normalizedEntity;
                }
                return;
            }

            try {
                const { plaintext, key } = await decryptText(normalizedEntity.encrypted_data);
                const decryptedFields = JSON.parse(plaintext);
                delete decryptedFields.encrypted_data;
                const decryptedResult = {
                    ...normalizedEntity,
                    ...decryptedFields,
                    _decrypted: true,
                    _decryption_key: key
                };
                if (active) {
                    setDecryptedEntity(decryptedResult);
                    displayEntityRef.current = decryptedResult;
                }
            } catch (err) {
                const lockedResult = {
                    ...normalizedEntity,
                    display: `🔒 [Encrypted ${normalizedEntity.type || 'Entity'}]`,
                    description: 'Unlock vault with correct passphrase to decrypt contents.',
                    _decrypted: false
                };
                if (active) {
                    setDecryptedEntity(lockedResult);
                    displayEntityRef.current = lockedResult;
                }
            }
        };

        decrypt();

        return () => { active = false; };
    }, [entity, isVisible, encryptionKeys]);

    useEffect(() => {
        if (decryptedEntity) {
            setEditedEntity(prev => {
                if (!prev || prev.id !== decryptedEntity.id) {
                    const copy = { ...decryptedEntity };
                    if (copy.id === 'new') {
                        copy.id = generateUUID();
                    }
                    return copy;
                }
                if (!isEditing) {
                    const copy = { ...decryptedEntity };
                    if (copy.id === 'new') {
                        copy.id = generateUUID();
                    }
                    return copy;
                }
                if (decryptedEntity._decrypted && !prev._decrypted) {
                    const copy = { ...decryptedEntity };
                    if (copy.id === 'new') {
                        copy.id = generateUUID();
                    }
                    return copy;
                }
                return prev;
            });
        } else {
            setEditedEntity(null);
        }
    }, [decryptedEntity, isEditing]);


    useEffect(() => {
        if (!displayEntity?.description) {
            setProcessedDescription('');
            return;
        }

        if (!displayEntity._decrypted) {
            setProcessedDescription(displayEntity.description);
            return;
        }

        let active = true;
        const blobUrlsToCleanup = [];

        const processHTML = async () => {
            try {
                const parser = new DOMParser();
                const doc = parser.parseFromString(displayEntity.description, 'text/html');
                const images = doc.querySelectorAll('img');
                const encImages = Array.from(images).filter(img => {
                    const src = img.getAttribute('src');
                    return src && src.includes('.enc') && !src.startsWith('blob:');
                });

                if (encImages.length === 0) {
                    if (active) setProcessedDescription(displayEntity.description);
                    return;
                }

                for (const img of encImages) {
                    const src = img.getAttribute('src');
                    try {
                        const response = await fetch(getMediaUrl(src));
                        if (response.ok) {
                            const encryptedBlob = await response.blob();
                            let mimeType = 'image/jpeg';
                            if (src.toLowerCase().includes('.png')) mimeType = 'image/png';
                            if (src.toLowerCase().includes('.gif')) mimeType = 'image/gif';
                            if (src.toLowerCase().includes('.webp')) mimeType = 'image/webp';

                            const decryptedBlob = await decryptBlob(encryptedBlob, mimeType, displayEntity._decryption_key);
                            const objectUrl = URL.createObjectURL(decryptedBlob);
                            blobUrlsToCleanup.push(objectUrl);
                            img.setAttribute('src', objectUrl);
                        }
                    } catch (err) {
                        console.error('Failed to decrypt read-only inline image:', err);
                    }
                }

                if (active) {
                    descriptionBlobUrlsRef.current.forEach(url => URL.revokeObjectURL(url));
                    descriptionBlobUrlsRef.current = blobUrlsToCleanup;
                    setProcessedDescription(doc.body.innerHTML);
                } else {
                    blobUrlsToCleanup.forEach(url => URL.revokeObjectURL(url));
                }
            } catch (err) {
                console.error('Error parsing/decrypting description:', err);
                if (active) setProcessedDescription(displayEntity.description);
            }
        };

        processHTML();

        return () => {
            active = false;
        };
    }, [isEditing, displayEntity?.description, displayEntity?._decrypted, displayEntity?._decryption_key]);

    useEffect(() => {
        return () => {
            descriptionBlobUrlsRef.current.forEach(url => URL.revokeObjectURL(url));
        };
    }, []);

    useEffect(() => {
        if (viewMode === 'relations' && entity) {
            fetchRelations();
        }
    }, [viewMode, entity]);

    const handleClose = () => {
        setIsAnimating(false);
        setTimeout(() => {
            onClose();
        }, 300);
    };

    const handleEdit = () => {
        setIsEditing(true);
        if (entity?.id && entity.id !== 'new') {
            // Preserve current view mode when entering edit mode
            const currentPath = viewMode === 'relations' ? '/relations' : '';
            navigate(`/entity/${entity.id}${currentPath}/edit`);
        }
    };

    const handleCancelEdit = () => {
        setEditedEntity(displayEntityRef.current);
        setIsEditing(false);
        setNewPhotos([]);
        setNewAttachments([]);
        setDeletedPhotos([]);
        setDeletedAttachments([]);
        if (entity?.id && entity.id !== 'new') {
            navigate(`/entity/${entity.id}`);
        }
    };

    const handleDelete = async () => {
        if (!entity || entity.isNew) return;

        const confirmMessage = `Are you sure you want to delete "${entity.display || 'this entity'}"?\n\nThis action cannot be undone.`;
        if (!confirm(confirmMessage)) return;

        try {
            const endpoint = entity.type === 'Person'
                ? `/api/people/${entity.id}/`
                : entity.type === 'Note'
                ? `/api/notes/${entity.id}/`
                : entity.type === 'Location'
                ? `/api/locations/${entity.id}/`
                : entity.type === 'Movie'
                ? `/api/movies/${entity.id}/`
                : entity.type === 'Book'
                ? `/api/books/${entity.id}/`
                : entity.type === 'Container'
                ? `/api/containers/${entity.id}/`
                : entity.type === 'Asset'
                ? `/api/assets/${entity.id}/`
                : entity.type === 'Org'
                ? `/api/orgs/${entity.id}/`
                : `/api/entities/${entity.id}/`;

            const response = await api.fetch(endpoint, {
                method: 'DELETE',
            });

            if (response.ok) {
                // Close the panel
                onClose();
                // Notify parent to remove from list (if needed)
                if (onUpdate) {
                    onUpdate({ ...entity, _deleted: true });
                }
            } else {
                const errorData = await response.json();
                console.error('Failed to delete entity:', errorData);
                alert(`Failed to delete entity: ${JSON.stringify(errorData)}`);
            }
        } catch (error) {
            console.error('Error deleting entity:', error);
            alert('Error deleting entity');
        }
    };

    const handleFieldChange = (field, value) => {
        setEditedEntity(prev => ({
            ...prev,
            [field]: value
        }));
    };

    const handlePhotoSelect = (e) => {
        const files = Array.from(e.target.files);
        setNewPhotos(prev => [...prev, ...files]);
    };

    const handleAttachmentSelect = (e) => {
        const files = Array.from(e.target.files);
        setNewAttachments(prev => [...prev, ...files]);
    };

    const addFilesFromDrop = useCallback((e, addFiles, filter = () => true) => {
        e.preventDefault();
        e.stopPropagation();
        if (e.dataTransfer.files?.length) {
            const files = Array.from(e.dataTransfer.files).filter(filter);
            if (files.length) addFiles((prev) => [...prev, ...files]);
        } else if (e.dataTransfer.items) {
            for (let i = 0; i < e.dataTransfer.items.length; i++) {
                const item = e.dataTransfer.items[i];
                if (item.kind === 'file') {
                    const file = item.getAsFile();
                    if (file && filter(file)) addFiles((prev) => [...prev, file]);
                } else if (item.kind === 'string' && item.type === 'text/uri-list') {
                    item.getAsString((url) => {
                        fetch(url, { mode: 'cors' })
                            .then((r) => r.blob())
                            .then((blob) => {
                                const ext = (blob.type || '').split('/')[1] || 'png';
                                const file = new File([blob], `image.${ext}`, { type: blob.type || 'image/png' });
                                if (filter(file)) addFiles((prev) => [...prev, file]);
                            })
                            .catch(() => {});
                    });
                    break;
                }
            }
        }
    }, []);

    const handlePhotoDrop = useCallback((e) => {
        setIsDraggingPhotos(false);
        if (!isEditing) return;
        addFilesFromDrop(e, setNewPhotos, (f) => f.type?.startsWith('image/'));
    }, [isEditing, addFilesFromDrop]);

    const handleAttachmentDrop = useCallback((e) => {
        setIsDraggingAttachments(false);
        if (!isEditing) return;
        addFilesFromDrop(e, setNewAttachments);
    }, [isEditing, addFilesFromDrop]);

    const handleDeletePhoto = (photo) => {
        setDeletedPhotos(prev => [...prev, photo]);
        setEditedEntity(prev => ({
            ...prev,
            photos: (prev.photos || []).filter(p => {
                const pUrl = typeof p === 'string' ? p : p.url;
                const photoUrl = typeof photo === 'string' ? photo : photo.url;
                return pUrl !== photoUrl;
            })
        }));
    };

    const handleDeleteNewPhoto = (index) => {
        setNewPhotos(prev => prev.filter((_, i) => i !== index));
    };

    const handleDeleteAttachment = (attachment) => {
        setDeletedAttachments(prev => [...prev, attachment]);
        setEditedEntity(prev => ({
            ...prev,
            attachments: (prev.attachments || []).filter(a => {
                const aUrl = typeof a === 'string' ? a : a.url;
                const attachmentUrl = typeof attachment === 'string' ? attachment : attachment.url;
                return aUrl !== attachmentUrl;
            })
        }));
    };

    const handleDeleteNewAttachment = (index) => {
        setNewAttachments(prev => prev.filter((_, i) => i !== index));
    };

    const movePhotoUp = (index) => {
        if (index === 0) return;
        setEditedEntity(prev => {
            const photos = [...(prev.photos || [])];
            [photos[index - 1], photos[index]] = [photos[index], photos[index - 1]];
            return { ...prev, photos };
        });
    };

    const movePhotoDown = (index) => {
        const photos = editedEntity.photos || [];
        if (index === photos.length - 1) return;
        setEditedEntity(prev => {
            const photos = [...(prev.photos || [])];
            [photos[index], photos[index + 1]] = [photos[index + 1], photos[index]];
            return { ...prev, photos };
        });
    };

    const moveAttachmentUp = (index) => {
        if (index === 0) return;
        setEditedEntity(prev => {
            const attachments = [...(prev.attachments || [])];
            [attachments[index - 1], attachments[index]] = [attachments[index], attachments[index - 1]];
            return { ...prev, attachments };
        });
    };

    const moveAttachmentDown = (index) => {
        const attachments = editedEntity.attachments || [];
        if (index === attachments.length - 1) return;
        setEditedEntity(prev => {
            const attachments = [...(prev.attachments || [])];
            [attachments[index], attachments[index + 1]] = [attachments[index + 1], attachments[index]];
            return { ...prev, attachments };
        });
    };

    // Location helpers
    const getGoogleMapsUrl = (loc) => {
        const lat = loc?.latitude ?? loc?.lat;
        const lon = loc?.longitude ?? loc?.lon;
        if (lat != null && lon != null) {
            return `https://www.google.com/maps?q=${lat},${lon}`;
        }
        const name = loc?.name || '';
        if (name) {
            return `https://www.google.com/maps/search/?api=1&query=${encodeURIComponent(name)}`;
        }
        return null;
    };

    const handleLocationChange = (idx, field, value) => {
        setEditedEntity(prev => {
            const locs = [...(prev.locations || [])];
            const loc = { ...(locs[idx] || {}), [field]: value };
            locs[idx] = loc;
            return { ...prev, locations: locs };
        });
    };

    const handleLookupCoords = async (idx) => {
        const loc = editedEntity.locations?.[idx] || {};
        const name = loc.name || '';
        if (!name.trim()) return;
        setGeocodeLoading({ idx, type: 'forward' });
        try {
            const r = await api.fetch(`/api/geocode/forward/?q=${encodeURIComponent(name)}`);
            const data = await r.json();
            if (r.ok && data.latitude != null && data.longitude != null) {
                setEditedEntity(prev => {
                    const locs = [...(prev.locations || [])];
                    locs[idx] = {
                        ...(locs[idx] || {}),
                        latitude: data.latitude,
                        longitude: data.longitude,
                        name: data.name || name,
                        ...(data.elevation != null && { elevation: data.elevation }),
                    };
                    return { ...prev, locations: locs };
                });
            } else {
                alert(data.error || 'Could not find coordinates');
            }
        } catch (e) {
            alert('Geocoding failed');
        } finally {
            setGeocodeLoading(null);
        }
    };

    const handleLookupName = async (idx) => {
        const loc = editedEntity.locations?.[idx] || {};
        const lat = loc.latitude ?? loc.lat;
        const lon = loc.longitude ?? loc.lon;
        if (lat == null || lon == null) return;
        setGeocodeLoading({ idx, type: 'reverse' });
        try {
            const r = await api.fetch(`/api/geocode/reverse/?lat=${lat}&lon=${lon}`);
            const data = await r.json();
            if (r.ok && data.name) {
                setEditedEntity(prev => {
                    const locs = [...(prev.locations || [])];
                    locs[idx] = { ...(locs[idx] || {}), name: data.name };
                    return { ...prev, locations: locs };
                });
            } else {
                alert(data.error || 'Could not find place name');
            }
        } catch (e) {
            alert('Reverse geocoding failed');
        } finally {
            setGeocodeLoading(null);
        }
    };

    const addLocation = () => {
        setEditedEntity(prev => ({
            ...prev,
            locations: [...(prev.locations || []), { name: '', latitude: null, longitude: null }]
        }));
    };

    const removeLocation = (idx) => {
        setEditedEntity(prev => ({
            ...prev,
            locations: (prev.locations || []).filter((_, i) => i !== idx)
        }));
    };

    const moveLocationUp = (idx) => {
        if (idx === 0) return;
        setEditedEntity(prev => {
            const locs = [...(prev.locations || [])];
            [locs[idx - 1], locs[idx]] = [locs[idx], locs[idx - 1]];
            return { ...prev, locations: locs };
        });
    };

    const moveLocationDown = (idx) => {
        const locs = editedEntity.locations || [];
        if (idx >= locs.length - 1) return;
        setEditedEntity(prev => {
            const arr = [...(prev.locations || [])];
            [arr[idx], arr[idx + 1]] = [arr[idx + 1], arr[idx]];
            return { ...prev, locations: arr };
        });
    };

    // Relations Management
    const fetchRelations = async () => {
        if (!entity) return;
        setIsLoadingRelations(true);
        try {
            const response = await api.fetch(`/api/entities/${entity.id}/relations/`);
            if (response.ok) {
                const data = await response.json();
                setRelations(data);
            }
        } catch (error) {
            console.error('Failed to fetch relations:', error);
        } finally {
            setIsLoadingRelations(false);
        }
    };

    // Relation schema - defines which entity types can be related
    const RELATION_SCHEMA = [
        { key: 'IS_CHILD_OF', reverseKey: 'IS_PARENT_OF', fromEntity: 'Person', toEntity: 'Person' },
        { key: 'IS_FRIEND_OF', reverseKey: 'IS_FRIEND_OF', fromEntity: 'Person', toEntity: 'Person' },
        { key: 'IS_COLLEAGUE_OF', reverseKey: 'IS_COLLEAGUE_OF', fromEntity: 'Person', toEntity: 'Person' },
        { key: 'IS_SPOUSE_OF', reverseKey: 'IS_SPOUSE_OF', fromEntity: 'Person', toEntity: 'Person' },
        { key: 'IS_MANAGER_OF', reverseKey: 'WORKS_FOR_MGR', fromEntity: 'Person', toEntity: 'Person' },
        { key: 'IS_STUDENT_OF', reverseKey: 'IS_TEACHER_OF', fromEntity: 'Person', toEntity: 'Person' },
        { key: 'HAS_STUDENT', reverseKey: 'IS_STUDENT_OF', fromEntity: 'Person', toEntity: 'Person' },
        { key: 'IS_STUDENT_OF', reverseKey: 'HAS_STUDENT', fromEntity: 'Person', toEntity: 'Org' },
        { key: 'IS_RELATED_TO', reverseKey: 'IS_RELATED_TO', fromEntity: '*', toEntity: '*' },
        { key: 'LIVES_AT', reverseKey: 'HAS_RESIDENT', fromEntity: 'Person', toEntity: 'Location' },
        { key: 'IS_LOCATED_IN', reverseKey: 'CONTAINS', fromEntity: 'Location', toEntity: 'Location' },
        { key: 'HAS_ACTOR', reverseKey: 'ACTED_IN', fromEntity: 'Movie', toEntity: 'Person' },
        { key: 'HAS_DIRECTOR', reverseKey: 'DIRECTED', fromEntity: 'Movie', toEntity: 'Person' },
        { key: 'HAS_MUS_DIRECTOR', reverseKey: 'GAVE_MUSIC_TO', fromEntity: 'Movie', toEntity: 'Person' },
        { key: 'INSPIRED', reverseKey: 'IS_BASED_ON', fromEntity: 'Book', toEntity: 'Movie' },
        { key: 'HAS_AS_AUTHOR', reverseKey: 'IS_AUTHOR_OF', fromEntity: 'Book', toEntity: 'Person' },
        { key: 'IS_LOCATED_IN', reverseKey: 'IS_LOCATION_OF', fromEntity: 'Book', toEntity: 'Location' },
        { key: 'IS_CONTAINED_IN', reverseKey: 'CONTAINS', fromEntity: 'Container', toEntity: 'Container' },
        { key: 'IS_LOCATED_IN', reverseKey: 'CONTAINS', fromEntity: 'Container', toEntity: 'Location' },
        { key: 'IS_LOCATED_IN', reverseKey: 'CONTAINS', fromEntity: 'Asset', toEntity: 'Container' },
        { key: 'IS_LOCATED_AT', reverseKey: 'HAS', fromEntity: 'Org', toEntity: 'Location' },
        { key: 'HAS_EMPLOYEE', reverseKey: 'WORKS_AT', fromEntity: 'Org', toEntity: 'Person' },
        { key: 'HAS_MEMBER', reverseKey: 'IS_MEMBER_OF', fromEntity: 'Org', toEntity: 'Person' },
        { key: 'HAS_STUDENT', reverseKey: 'STUDIES_AT', fromEntity: 'Org', toEntity: 'Person' }
    ];

    // Get valid entity types that can be related to the current entity
    const getValidEntityTypes = (currentEntityType) => {
        const validTypes = new Set();

        RELATION_SCHEMA.forEach(schema => {
            // Check forward direction
            if (schema.fromEntity === currentEntityType || schema.fromEntity === '*') {
                if (schema.toEntity === '*') {
                    // Can relate to any type
                    ['Person', 'Location', 'Movie', 'Book', 'Container', 'Asset', 'Org', 'Note'].forEach(t => validTypes.add(t));
                } else {
                    validTypes.add(schema.toEntity);
                }
            }
            // Check reverse direction
            if (schema.toEntity === currentEntityType || schema.toEntity === '*') {
                if (schema.fromEntity === '*') {
                    ['Person', 'Location', 'Movie', 'Book', 'Container', 'Asset', 'Org', 'Note'].forEach(t => validTypes.add(t));
                } else {
                    validTypes.add(schema.fromEntity);
                }
            }
        });

        return Array.from(validTypes);
    };

    // Get valid relation types between two entity types
    const getValidRelationTypes = (fromType, toType) => {
        const validRelations = [];

        RELATION_SCHEMA.forEach(schema => {
            // Check forward direction
            if ((schema.fromEntity === fromType || schema.fromEntity === '*') &&
                (schema.toEntity === toType || schema.toEntity === '*')) {
                validRelations.push(schema.key);
            }
            // Check reverse direction
            if ((schema.toEntity === fromType || schema.toEntity === '*') &&
                (schema.fromEntity === toType || schema.fromEntity === '*')) {
                validRelations.push(schema.reverseKey);
            }
        });

        // Remove duplicates
        return [...new Set(validRelations)];
    };

    const searchEntities = async (query) => {
        setEntitySearchQuery(query);

        if (!query || query.length < 2) {
            setEntitySearchResults([]);
            return;
        }
        try {
            const validTypes = getValidEntityTypes(entity.type);
            const typeQuery = validTypes.length > 0
                ? `&type=${encodeURIComponent(validTypes.join(','))}`
                : '';
            const response = await api.fetch(`/api/search/?q=${encodeURIComponent(query)}${typeQuery}`);
            if (response.ok) {
                const data = await response.json();
                const results = Array.isArray(data) ? data : (data.results || []);
                setEntitySearchResults(results);
            }
        } catch (error) {
            console.error('Failed to search entities:', error);
        }
    };

    const fetchAvailableRelationTypes = () => {
        // If a target entity is selected, filter relation types based on both entity types
        if (newRelation.targetEntityData) {
            const validRelations = getValidRelationTypes(entity.type, newRelation.targetEntityData.type);
            setAvailableRelationTypes(validRelations);
        } else {
            // No target entity selected yet - show all possible relations for current entity
            const allRelations = new Set();
            const validTypes = getValidEntityTypes(entity.type);

            validTypes.forEach(targetType => {
                const relations = getValidRelationTypes(entity.type, targetType);
                relations.forEach(rel => allRelations.add(rel));
            });

            setAvailableRelationTypes(Array.from(allRelations));
        }
    };

    const handleAddRelation = async () => {
        if (!newRelation.targetEntity || !newRelation.relationType) {
            alert('Please select an entity and relation type');
            return;
        }

        try {
            const relationData = {
                from_entity: entity.id,
                to_entity: newRelation.targetEntity,
                relation_type: newRelation.relationType
            };

            const response = await api.fetch('/api/relations/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(relationData)
            });

            if (response.ok) {
                setIsAddingRelation(false);
                setNewRelation({ targetEntity: '', relationType: '', targetEntityData: null });
                setEntitySearchResults([]);
                setEntitySearchQuery('');
                fetchRelations(); // Refresh relations list
            } else {
                const error = await response.json();
                alert(`Failed to add relation: ${JSON.stringify(error)}`);
            }
        } catch (error) {
            console.error('Error adding relation:', error);
            alert('Error adding relation');
        }
    };

    const handleDeleteRelation = async (relationId) => {
        if (!confirm('Are you sure you want to delete this relation?')) return;

        try {
            const response = await api.fetch(`/api/relations/${relationId}/`, {
                method: 'DELETE'
            });

            if (response.ok) {
                fetchRelations(); // Refresh relations list
            } else {
                alert('Failed to delete relation');
            }
        } catch (error) {
            console.error('Error deleting relation:', error);
            alert('Error deleting relation');
        }
    };

    useEffect(() => {
        if (isAddingRelation) {
            fetchAvailableRelationTypes();
        }
    }, [isAddingRelation]);

    const uploadFile = async (file) => {
        const formData = new FormData();
        formData.append('file', file);

        const response = await api.fetch('/api/upload/', {
            method: 'POST',
            body: formData,
        });

        if (!response.ok) {
            throw new Error('File upload failed');
        }

        const data = await response.json();
        // Return the full response object with url, thumbnail_url, etc.
        return data;
    };

    const handleSave = async () => {
        if (editedEntity.is_encrypted && !hasKeys) {
            alert('Vault is locked. Please enter a passphrase to unlock or set the key before saving an encrypted entity.');
            return;
        }

        setIsSaving(true);
        try {
            // 1. Helpers for file conversion
            const fetchFileAsBlob = async (url) => {
                const targetUrl = url.startsWith('http') ? url : getMediaUrl(url);
                const response = await fetch(targetUrl);
                if (!response.ok) throw new Error(`Failed to fetch file: ${url}`);
                return await response.blob();
            };

            const convertFileToEncrypted = async (fileUrl, fileName) => {
                const blob = await fetchFileAsBlob(fileUrl);
                const encryptedBlob = await encryptBlob(blob);
                const encryptedFile = new File([encryptedBlob], fileName + '.enc', { type: 'application/octet-stream' });
                return await uploadFile(encryptedFile);
            };

            const convertFileToDecrypted = async (fileUrl, fileName) => {
                const blob = await fetchFileAsBlob(fileUrl);
                let mimeType = 'application/octet-stream';
                const cleanName = fileName.replace(/\.enc$/, '');
                if (cleanName.toLowerCase().endsWith('.png')) mimeType = 'image/png';
                else if (cleanName.toLowerCase().endsWith('.jpg') || cleanName.toLowerCase().endsWith('.jpeg')) mimeType = 'image/jpeg';
                else if (cleanName.toLowerCase().endsWith('.gif')) mimeType = 'image/gif';
                else if (cleanName.toLowerCase().endsWith('.webp')) mimeType = 'image/webp';
                else if (cleanName.toLowerCase().endsWith('.pdf')) mimeType = 'application/pdf';
                
                const decryptedBlob = await decryptBlob(blob, mimeType);
                const decryptedFile = new File([decryptedBlob], cleanName, { type: mimeType });
                return await uploadFile(decryptedFile);
            };

            const uploadScopedFile = async (file, entityId) => {
                const formData = new FormData();
                formData.append('file', file);
                if (entityId) {
                    formData.append('entity_id', entityId);
                }
                const response = await api.fetch('/api/upload/', {
                    method: 'POST',
                    body: formData,
                });
                if (!response.ok) throw new Error('Scoped file upload failed');
                return await response.json();
            };

            const convertInlineImageToEncrypted = async (fileUrl, fileName, entityId) => {
                const blob = await fetchFileAsBlob(fileUrl);
                const encryptedBlob = await encryptBlob(blob);
                const encryptedFile = new File([encryptedBlob], fileName + '.enc', { type: 'application/octet-stream' });
                return await uploadScopedFile(encryptedFile, entityId);
            };

            const convertInlineImageToDecrypted = async (fileUrl, fileName, entityId) => {
                const blob = await fetchFileAsBlob(fileUrl);
                let mimeType = 'application/octet-stream';
                if (fileName.toLowerCase().endsWith('.png')) mimeType = 'image/png';
                else if (fileName.toLowerCase().endsWith('.jpg') || fileName.toLowerCase().endsWith('.jpeg')) mimeType = 'image/jpeg';
                else if (fileName.toLowerCase().endsWith('.gif')) mimeType = 'image/gif';
                else if (fileName.toLowerCase().endsWith('.webp')) mimeType = 'image/webp';
                
                const decryptedBlob = await decryptBlob(blob, mimeType);
                const decryptedFile = new File([decryptedBlob], fileName, { type: mimeType });
                return await uploadScopedFile(decryptedFile, entityId);
            };

            // Helper to encrypt and upload files if encryption is toggled ON
            const encryptAndUpload = async (file) => {
                if (editedEntity.is_encrypted) {
                    const encryptedBlob = await encryptBlob(file);
                    // Name file with .enc so the backend skips thumbnailing (which would fail anyway)
                    const encryptedFile = new File([encryptedBlob], file.name + '.enc', { type: 'application/octet-stream' });
                    return await uploadFile(encryptedFile);
                }
                return await uploadFile(file);
            };

            // Upload new photos and store full metadata
            const uploadedPhotos = [];
            for (const file of newPhotos) {
                try {
                    const uploadResult = await encryptAndUpload(file);
                    // Store object with url, original filename, and caption
                    uploadedPhotos.push({
                        url: uploadResult.url,
                        thumbnail_url: uploadResult.thumbnail_url || uploadResult.url,
                        filename: file.name, // Store original filename
                        caption: file.caption || '', // Store caption if provided
                    });
                } catch (error) {
                    console.error('Failed to upload photo:', error);
                }
            }

            // Upload new attachments and store full metadata
            const uploadedAttachments = [];
            for (const file of newAttachments) {
                try {
                    const uploadResult = await encryptAndUpload(file);
                    // Store object with url, original filename, caption
                    const attachmentData = {
                        url: uploadResult.url,
                        filename: file.name, // Store original filename
                        caption: file.caption || '', // Store caption if provided
                    };
                    if (uploadResult.thumbnail_url) {
                        attachmentData.thumbnail_url = uploadResult.thumbnail_url;
                    }
                    if (uploadResult.preview_url) {
                        attachmentData.preview_url = uploadResult.preview_url;
                    }
                    uploadedAttachments.push(attachmentData);
                } catch (error) {
                    console.error('Failed to upload attachment:', error);
                }
            }

            // Combine existing and new photos/attachments
            const updatedPhotos = [
                ...(editedEntity.photos || []),
                ...uploadedPhotos
            ];

            const updatedAttachments = [
                ...(editedEntity.attachments || []),
                ...uploadedAttachments
            ];

            const targetEncrypted = editedEntity.is_encrypted;

            // Convert encryption of existing photos if target state changed
            const finalPhotos = [];
            for (const photo of updatedPhotos) {
                const isPhotoEncrypted = photo.url.endsWith('.enc');
                const originalFilename = photo.filename || photo.url.substring(photo.url.lastIndexOf('/') + 1);
                
                if (targetEncrypted && !isPhotoEncrypted) {
                    try {
                        const uploadResult = await convertFileToEncrypted(photo.url, originalFilename);
                        finalPhotos.push({
                            ...photo,
                            url: uploadResult.url,
                            thumbnail_url: uploadResult.thumbnail_url || uploadResult.url,
                            filename: originalFilename + '.enc'
                        });
                    } catch (err) {
                        console.error('Failed to convert photo to encrypted:', err);
                        finalPhotos.push(photo);
                    }
                } else if (!targetEncrypted && isPhotoEncrypted) {
                    try {
                        const cleanName = originalFilename.replace(/\.enc$/, '');
                        const uploadResult = await convertFileToDecrypted(photo.url, originalFilename);
                        finalPhotos.push({
                            ...photo,
                            url: uploadResult.url,
                            thumbnail_url: uploadResult.thumbnail_url || uploadResult.url,
                            filename: cleanName
                        });
                    } catch (err) {
                        console.error('Failed to convert photo to decrypted:', err);
                        finalPhotos.push(photo);
                    }
                } else {
                    finalPhotos.push(photo);
                }
            }

            // Convert encryption of existing attachments if target state changed
            const finalAttachments = [];
            for (const attachment of updatedAttachments) {
                const isAttachmentEncrypted = attachment.url.endsWith('.enc');
                const originalFilename = attachment.filename || attachment.url.substring(attachment.url.lastIndexOf('/') + 1);
                
                if (targetEncrypted && !isAttachmentEncrypted) {
                    try {
                        const uploadResult = await convertFileToEncrypted(attachment.url, originalFilename);
                        const attachmentData = {
                            ...attachment,
                            url: uploadResult.url,
                            filename: originalFilename + '.enc'
                        };
                        if (uploadResult.thumbnail_url) attachmentData.thumbnail_url = uploadResult.thumbnail_url;
                        if (uploadResult.preview_url) attachmentData.preview_url = uploadResult.preview_url;
                        finalAttachments.push(attachmentData);
                    } catch (err) {
                        console.error('Failed to convert attachment to encrypted:', err);
                        finalAttachments.push(attachment);
                    }
                } else if (!targetEncrypted && isAttachmentEncrypted) {
                    try {
                        const cleanName = originalFilename.replace(/\.enc$/, '');
                        const uploadResult = await convertFileToDecrypted(attachment.url, originalFilename);
                        const attachmentData = {
                            ...attachment,
                            url: uploadResult.url,
                            filename: cleanName
                        };
                        if (uploadResult.thumbnail_url) attachmentData.thumbnail_url = uploadResult.thumbnail_url;
                        if (uploadResult.preview_url) attachmentData.preview_url = uploadResult.preview_url;
                        if (!uploadResult.thumbnail_url) delete attachmentData.thumbnail_url;
                        if (!uploadResult.preview_url) delete attachmentData.preview_url;
                        finalAttachments.push(attachmentData);
                    } catch (err) {
                        console.error('Failed to convert attachment to decrypted:', err);
                        finalAttachments.push(attachment);
                    }
                } else {
                    finalAttachments.push(attachment);
                }
            }

            // Convert encryption and scope directory of description inline images
            let finalDescription = editedEntity.description || '';
            const activeScopedFiles = [];
            
            if (finalDescription) {
                const parser = new DOMParser();
                const doc = parser.parseFromString(finalDescription, 'text/html');
                const imgElements = Array.from(doc.querySelectorAll('img'));
                
                for (const imgElement of imgElements) {
                    const src = imgElement.getAttribute('src');
                    if (src && src.includes('/media/')) {
                        const urlPath = src.split('/media/')[1];
                        const cleanPath = urlPath.split('?')[0].split('#')[0];
                        const isImgEncrypted = cleanPath.endsWith('.enc');
                        const originalFilename = cleanPath.substring(cleanPath.lastIndexOf('/') + 1);
                        
                        if (targetEncrypted && !isImgEncrypted) {
                            try {
                                const cleanName = originalFilename;
                                const uploadResult = await convertInlineImageToEncrypted(src, cleanName, editedEntity.id);
                                imgElement.setAttribute('src', getMediaUrl(uploadResult.url));
                                activeScopedFiles.push(uploadResult.name);
                            } catch (err) {
                                console.error('Failed to convert inline image to encrypted:', err);
                                activeScopedFiles.push(originalFilename);
                            }
                        } else if (!targetEncrypted && isImgEncrypted) {
                            try {
                                const cleanName = originalFilename.replace(/\.enc$/, '');
                                const uploadResult = await convertInlineImageToDecrypted(src, cleanName, editedEntity.id);
                                imgElement.setAttribute('src', getMediaUrl(uploadResult.url));
                                activeScopedFiles.push(uploadResult.name);
                            } catch (err) {
                                console.error('Failed to convert inline image to decrypted:', err);
                                activeScopedFiles.push(originalFilename);
                            }
                        } else {
                            activeScopedFiles.push(originalFilename);
                        }
                    }
                }
                
                finalDescription = doc.body.innerHTML;
            }
            
            editedEntity.description = finalDescription;

            // Compile referenced_files metadata
            const referencedFiles = [];
            finalPhotos.forEach(p => {
                if (p.url) {
                    const path = p.url.replace(/^\/?media\//, '');
                    referencedFiles.push({ path, is_encrypted: targetEncrypted });
                }
            });
            finalAttachments.forEach(a => {
                if (a.url) {
                    const path = a.url.replace(/^\/?media\//, '');
                    referencedFiles.push({ path, is_encrypted: targetEncrypted });
                }
            });

            // Generate display name for encrypted entities before encryption,
            // since the backend will receive placeholders and cannot generate it.
            if (editedEntity.is_encrypted) {
                let computedDisplay = editedEntity.display;
                if (!computedDisplay || computedDisplay.startsWith('🔒')) {
                    if (editedEntity.type === 'Person') {
                        computedDisplay = `${editedEntity.first_name || ''} ${editedEntity.last_name || ''}`.trim() || 'Person';
                    } else if (editedEntity.type === 'Note') {
                        const desc = editedEntity.description || '';
                        const cleanDesc = desc.replace(/<[^>]*>/g, '');
                        computedDisplay = cleanDesc.length > 50 ? (cleanDesc.substring(0, 50) + '...') : (cleanDesc || 'Note');
                    } else if (editedEntity.type === 'Location') {
                        const parts = [];
                        if (editedEntity.address1) parts.push(editedEntity.address1);
                        if (editedEntity.city) parts.push(editedEntity.city);
                        if (editedEntity.state) parts.push(editedEntity.state);
                        if (editedEntity.country) parts.push(editedEntity.country);
                        computedDisplay = parts.join(', ') || 'Location';
                    } else if (editedEntity.type === 'Movie') {
                        computedDisplay = 'Untitled Movie';
                    } else if (editedEntity.type === 'Book') {
                        computedDisplay = 'Untitled Book';
                    } else if (editedEntity.type === 'Container') {
                        computedDisplay = 'Untitled Container';
                    } else if (editedEntity.type === 'Asset') {
                        computedDisplay = 'Untitled Asset';
                    } else if (editedEntity.type === 'Org') {
                        computedDisplay = editedEntity.name || 'Untitled Organization';
                    }
                }
                editedEntity.display = computedDisplay;
            }

            const dataToSave = {
                ...editedEntity,
                photos: finalPhotos,
                attachments: finalAttachments,
                referenced_files: referencedFiles,
                active_scoped_files: activeScopedFiles
            };

            // Remove temporary flags and invalid id for new entities
            delete dataToSave.isNew;
            if (dataToSave.id === null || dataToSave.id === 'new') {
                delete dataToSave.id;
            }

            // Clean up empty/null fields to avoid validation errors
            Object.keys(dataToSave).forEach(key => {
                const value = dataToSave[key];
                if (key === 'locations') return; // Always send locations (including [])
                if (value === '' || value === null ||
                    (Array.isArray(value) && value.length === 0)) {
                    delete dataToSave[key];
                }
            });

            // Encrypt payload if Secure Vault Lock is enabled
            let finalPayload;
            let targetKey = null;
            if (editedEntity.is_encrypted) {
                targetKey = editedEntity._decryption_key || encryptionKeys[encryptionKeys.length - 1];
                
                const fieldsToEncrypt = {};
                const fieldsToKeep = [
                    'id', 'type', 'tags', 'is_encrypted', 'encrypted_data', 
                    'created_at', 'updated_at', '_decrypted', '_decryption_key',
                    'referenced_files', 'active_scoped_files'
                ];
                
                Object.keys(dataToSave).forEach(key => {
                    if (!fieldsToKeep.includes(key)) {
                        fieldsToEncrypt[key] = dataToSave[key];
                    }
                });

                const encryptedStr = await encryptText(JSON.stringify(fieldsToEncrypt), targetKey);

                finalPayload = {
                    id: dataToSave.id,
                    type: dataToSave.type,
                    tags: dataToSave.tags || [],
                    is_encrypted: true,
                    encrypted_data: encryptedStr,
                    display: `🔒 [Encrypted ${dataToSave.type || 'Entity'}]`,
                    description: '',
                    urls: [],
                    photos: [],
                    attachments: [],
                    locations: [],
                    referenced_files: dataToSave.referenced_files || [],
                    active_scoped_files: dataToSave.active_scoped_files || [],
                };

                // Clear/null subclass-specific fields on backend
                if (dataToSave.type === 'Person') {
                    Object.assign(finalPayload, {
                        first_name: null, last_name: null, dob: null,
                        gender: 'Unspecified', emails: [], phones: [], profession: null
                    });
                } else if (dataToSave.type === 'Note') {
                    Object.assign(finalPayload, { date: null });
                } else if (dataToSave.type === 'Location') {
                    Object.assign(finalPayload, {
                        address1: null, address2: null, postal_code: null,
                        city: null, state: null, country: null
                    });
                } else if (dataToSave.type === 'Movie') {
                    Object.assign(finalPayload, { year: null, language: null, country: null });
                } else if (dataToSave.type === 'Book') {
                    Object.assign(finalPayload, { year: null, language: null, country: null, summary: null });
                } else if (dataToSave.type === 'Asset') {
                    Object.assign(finalPayload, { value: null, acquired_on: null });
                } else if (dataToSave.type === 'Org') {
                    Object.assign(finalPayload, { name: null, kind: 'Unspecified' });
                }
            } else {
                finalPayload = {
                    ...dataToSave,
                    is_encrypted: false,
                    encrypted_data: null
                };
            }

            const isNewEntity = entity?.isNew === true;
            const method = isNewEntity ? 'POST' : 'PATCH';

            // Determine endpoint based on type and whether it's new or existing
            let endpoint;
            if (isNewEntity) {
                endpoint = editedEntity.type === 'Person'
                    ? `/api/people/`
                    : editedEntity.type === 'Note'
                    ? `/api/notes/`
                    : editedEntity.type === 'Location'
                    ? `/api/locations/`
                    : editedEntity.type === 'Movie'
                    ? `/api/movies/`
                    : editedEntity.type === 'Book'
                    ? `/api/books/`
                    : editedEntity.type === 'Container'
                    ? `/api/containers/`
                    : editedEntity.type === 'Asset'
                    ? `/api/assets/`
                    : editedEntity.type === 'Org'
                    ? `/api/orgs/`
                    : `/api/entities/`;
            } else {
                endpoint = editedEntity.type === 'Person'
                    ? `/api/people/${editedEntity.id}/`
                    : editedEntity.type === 'Note'
                    ? `/api/notes/${editedEntity.id}/`
                    : editedEntity.type === 'Location'
                    ? `/api/locations/${editedEntity.id}/`
                    : editedEntity.type === 'Movie'
                    ? `/api/movies/${editedEntity.id}/`
                    : editedEntity.type === 'Book'
                    ? `/api/books/${editedEntity.id}/`
                    : editedEntity.type === 'Container'
                    ? `/api/containers/${editedEntity.id}/`
                    : editedEntity.type === 'Asset'
                    ? `/api/assets/${editedEntity.id}/`
                    : editedEntity.type === 'Org'
                    ? `/api/orgs/${editedEntity.id}/`
                    : `/api/entities/${editedEntity.id}/`;
            }

            const response = await api.fetch(endpoint, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(finalPayload),
            });

            if (response.ok) {
                const savedEntity = await response.json();
                
                // Decrypt saved entity immediately to display in UI
                let decryptedSaved = savedEntity;
                if (savedEntity.is_encrypted) {
                    try {
                        const activeKey = targetKey || encryptionKeys[encryptionKeys.length - 1];
                        const { plaintext } = await decryptText(savedEntity.encrypted_data);
                        const decryptedFields = JSON.parse(plaintext);
                        delete decryptedFields.encrypted_data;
                        decryptedSaved = {
                            ...savedEntity,
                            ...decryptedFields,
                            _decrypted: true,
                            _decryption_key: activeKey
                        };
                    } catch (err) {
                        console.error('Failed to decrypt saved entity:', err);
                    }
                }

                displayEntityRef.current = decryptedSaved;
                setDecryptedEntity(decryptedSaved);
                setEditedEntity(decryptedSaved);
                setIsEditing(false);
                setNewPhotos([]);
                setNewAttachments([]);
                setDeletedPhotos([]);
                setDeletedAttachments([]);

                // Navigate to detail view after save
                if (decryptedSaved.id && decryptedSaved.id !== 'new') {
                    navigate(`/entity/${decryptedSaved.id}`);
                }

                // Notify parent component of the update or creation
                if (isNewEntity && onCreate) {
                    onCreate(decryptedSaved);
                } else if (onUpdate) {
                    onUpdate(decryptedSaved);
                }
            } else {
                const errorData = await response.json();
                console.error('Failed to save entity:', errorData);
                alert(`Failed to save changes: ${JSON.stringify(errorData)}`);
            }
        } catch (error) {
            console.error('Error saving entity:', error);
            alert('Error saving changes');
        } finally {
            setIsSaving(false);
        }
    };

    if (!shouldRender || !displayEntity) return null;

    // Helper to convert relative media URLs to full API URLs

    const formatDate = (dateString) => {
        if (!dateString) return 'N/A';
        return new Date(dateString).toLocaleString();
    };

    const renderHierarchicalTag = (tag) => {
        // Split tag by '/' to get parts
        const parts = tag.split('/');
        
        return (
            <div className="inline-flex items-center px-2 py-1 bg-blue-100 dark:bg-blue-900 rounded mr-2 mb-1">
                {parts.map((part, idx) => {
                    const tagPath = parts.slice(0, idx + 1).join('/');
                    const isLast = idx === parts.length - 1;
                    
                    return (
                        <React.Fragment key={idx}>
                            <button
                                onClick={() => {
                                    // Navigate to home with tag filter
                                    onUpdate({
                                        ...entity,
                                        _navigate: true,
                                        _viewMode: 'list',
                                        _tagFilter: tagPath
                                    });
                                }}
                                className="text-blue-800 dark:text-blue-200 hover:underline font-medium"
                            >
                                {part}
                            </button>
                            {!isLast && <span className="mx-1 text-blue-600 dark:text-blue-400">/</span>}
                        </React.Fragment>
                    );
                })}
            </div>
        );
    };

    const renderField = (label, value, isArray = false, isObject = false, isTags = false) => {
        if (!value || (isArray && (!Array.isArray(value) || value.length === 0))) {
            return null;
        }

        const valueBorder = "border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2";

        return (
            <div className="mb-4">
                <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                    {label}
                </h3>
                {isArray ? (
                    <div className={`space-y-1 ${valueBorder}`}>
                        {value.map((item, idx) => (
                            <div key={idx} className="text-gray-900 dark:text-gray-100">
                                {isObject ? (
                                    <div className="bg-gray-50 dark:bg-gray-700 p-2 rounded">
                                        {Object.entries(item).map(([k, v]) => (
                                            <div key={k}>
                                                <span className="font-medium">{k}:</span> {String(v)}
                                            </div>
                                        ))}
                                    </div>
                                ) : isTags ? (
                                    renderHierarchicalTag(item)
                                ) : (
                                    <span className="inline-block px-2 py-1 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded mr-2 mb-1">
                                        {item}
                                    </span>
                                )}
                            </div>
                        ))}
                    </div>
                ) : (
                    <p className={`text-gray-900 dark:text-gray-100 ${valueBorder}`}>{value}</p>
                )}
            </div>
        );
    };

    const renderEditableField = (label, fieldName, value, type = 'text', isTextArea = false) => {
        return (
            <div className="mb-4">
                <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                    {label}
                </label>
                {isTextArea ? (
                    <textarea
                        value={value || ''}
                        onChange={(e) => handleFieldChange(fieldName, e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                        rows={3}
                    />
                ) : (
                    <input
                        type={type}
                        value={value || ''}
                        onChange={(e) => handleFieldChange(fieldName, e.target.value)}
                        className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                    />
                )}
            </div>
        );
    };

    return (
        <>
            {/* Backdrop - fade in during slide-in, remove immediately on close */}
            {shouldRender && isAnimating && (
                <div
                    className="fixed inset-0 bg-black bg-opacity-30 z-40 animate-fade-in print:hidden"
                    onClick={handleClose}
                />
            )}

            {/* Detail Panel */}
            <div className={`fixed inset-0 bg-white dark:bg-gray-800 shadow-2xl z-50 overflow-y-auto transition-transform duration-300 ease-in-out print:overflow-visible ${
                isAnimating ? 'translate-x-0' : 'translate-x-full'
            }`}>
                {/* Header */}
                <div className="sticky top-0 bg-white dark:bg-gray-800 border-b border-gray-200 dark:border-gray-700 p-4 flex items-center justify-between z-10 print:static print:border-b-2">
                    <div className="flex-1 min-w-0">
                        <h2 className="text-2xl font-bold text-gray-900 dark:text-gray-100 truncate">
                            {entity?.isNew ? 'New Entity' : (displayEntity?.display || 'Untitled')}
                        </h2>
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
                            {entity?.isNew ? 'Create new entity' : displayEntity?.type}
                        </p>
                    </div>
                    <div className="flex items-center gap-2 ml-4">
                        {!isEditing ? (
                            <>
                                {(!displayEntity?.is_encrypted || displayEntity?._decrypted) && (
                                    <button
                                        onClick={handleEdit}
                                        className="px-3 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition text-sm font-medium"
                                        aria-label="Edit entity"
                                    >
                                        Edit
                                    </button>
                                )}
                                {!entity?.isNew && (
                                    <>
                                        <button
                                            onClick={() => window.print()}
                                            className="px-3 py-2 rounded-lg bg-green-600 text-white hover:bg-green-700 transition text-sm font-medium print:hidden"
                                            aria-label="Print entity"
                                            title="Print entity"
                                        >
                                            Print
                                        </button>
                                        <button
                                            onClick={handleDelete}
                                            className="px-3 py-2 rounded-lg bg-red-600 text-white hover:bg-red-700 transition text-sm font-medium"
                                            aria-label="Delete entity"
                                            title="Delete entity"
                                        >
                                            Delete
                                        </button>
                                    </>
                                )}
                                <button
                                    onClick={handleClose}
                                    className="p-2 rounded-full hover:bg-gray-100 dark:hover:bg-gray-700 transition"
                                    aria-label="Close detail panel"
                                >
                                    <svg
                                        xmlns="http://www.w3.org/2000/svg"
                                        className="h-6 w-6 text-gray-600 dark:text-gray-300"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                    >
                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                    </svg>
                                </button>
                            </>
                        ) : (
                            <>
                                <button
                                    onClick={handleSave}
                                    disabled={isSaving}
                                    className="px-3 py-2 rounded-lg bg-green-600 text-white hover:bg-green-700 transition text-sm font-medium disabled:bg-gray-400 disabled:cursor-not-allowed"
                                    aria-label="Save changes"
                                >
                                    {isSaving ? 'Saving...' : 'Save'}
                                </button>
                                <button
                                    onClick={handleCancelEdit}
                                    disabled={isSaving}
                                    className="px-3 py-2 rounded-lg bg-gray-300 dark:bg-gray-600 text-gray-900 dark:text-gray-100 hover:bg-gray-400 dark:hover:bg-gray-500 transition text-sm font-medium disabled:opacity-50"
                                    aria-label="Cancel editing"
                                >
                                    Cancel
                                </button>
                            </>
                        )}
                    </div>
                </div>

                {/* View Mode Toggle - Hide for new entities (they have no relations yet) */}
                {!entity?.isNew && (
                    <div className="border-b border-gray-200 dark:border-gray-700 px-4 print:hidden">
                        <div className="flex gap-1">
                            <button
                                onClick={() => {
                                    setViewMode('details');
                                    if (entity?.id && entity.id !== 'new') {
                                        navigate(`/entity/${entity.id}`);
                                    }
                                }}
                                className={`px-4 py-2 font-medium transition-colors border-b-2 ${
                                    viewMode === 'details'
                                        ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                                        : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                                }`}
                            >
                                Details
                            </button>
                            <button
                                onClick={() => {
                                    setViewMode('relations');
                                    if (entity?.id && entity.id !== 'new') {
                                        navigate(`/entity/${entity.id}/relations`);
                                    }
                                }}
                                className={`px-4 py-2 font-medium transition-colors border-b-2 ${
                                    viewMode === 'relations'
                                        ? 'border-blue-600 text-blue-600 dark:text-blue-400'
                                        : 'border-transparent text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-200'
                                }`}
                            >
                                Relations
                            </button>
                        </div>
                    </div>
                )}

                {/* Content */}
                <div className="p-6 space-y-6 print:space-y-8">
                    {displayEntity?.is_encrypted && !displayEntity?._decrypted && !entity?.isNew ? (
                        <div className="flex flex-col items-center justify-center py-12 px-4 text-center">
                            <div className="w-16 h-16 bg-blue-50 dark:bg-blue-900/30 rounded-full flex items-center justify-center mb-4 border border-blue-100 dark:border-blue-800">
                                <span className="text-3xl">🔒</span>
                            </div>
                            <h3 className="text-xl font-bold text-gray-900 dark:text-gray-100 mb-1">
                                Encrypted Content Locked
                            </h3>
                            <p className="text-sm text-gray-500 dark:text-gray-400 max-w-sm mb-6 font-normal">
                                This {displayEntity.type || 'entity'} is protected by Zero-Knowledge encryption. Enter the matching passphrase to unlock it.
                            </p>

                            <form
                                onSubmit={async (e) => {
                                    e.preventDefault();
                                    if (!vaultPassphrase.trim()) return;
                                    setIsInitializingKey(true);
                                    try {
                                        await deriveKey(vaultPassphrase);
                                        setVaultPassphrase('');
                                    } catch (err) {
                                        alert('Incorrect passphrase or key derivation failed.');
                                    } finally {
                                        setIsInitializingKey(false);
                                    }
                                }}
                                className="w-full max-w-sm flex flex-col gap-3"
                            >
                                <input
                                    type="password"
                                    placeholder="Enter passphrase to unlock"
                                    value={vaultPassphrase}
                                    onChange={(e) => setVaultPassphrase(e.target.value)}
                                    disabled={isInitializingKey}
                                    className="w-full px-4 py-2.5 rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-750 text-gray-900 dark:text-gray-100 focus:outline-none focus:ring-2 focus:ring-blue-500 text-center font-medium"
                                />
                                <button
                                    type="submit"
                                    disabled={isInitializingKey || !vaultPassphrase.trim()}
                                    className="w-full py-2.5 px-4 bg-blue-600 hover:bg-blue-700 disabled:bg-blue-400 text-white font-semibold rounded-xl shadow transition flex items-center justify-center gap-2"
                                >
                                    {isInitializingKey ? (
                                        <>
                                            <svg className="animate-spin h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                                                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                                                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                                            </svg>
                                            Unlocking...
                                        </>
                                    ) : 'Unlock'}
                                </button>
                            </form>

                            {/* Tags (Unencrypted metadata) */}
                            {displayEntity.tags && displayEntity.tags.length > 0 && (
                                <div className="mt-8 pt-6 border-t border-gray-200 dark:border-gray-700 w-full max-w-sm text-left">
                                    <h4 className="text-xs font-bold uppercase tracking-wider text-gray-400 dark:text-gray-500 mb-2">
                                        Tags (Unencrypted)
                                    </h4>
                                    <div className="flex flex-wrap">
                                        {displayEntity.tags.map((tag, idx) => renderHierarchicalTag(tag))}
                                    </div>
                                </div>
                            )}
                        </div>
                    ) : (
                        <>
                            {/* Details View */}
                            {(viewMode === 'details' || window.matchMedia('print').matches) && (
                        <>
                            {/* Basic Information */}
                            <section>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                            Basic Information
                        </h3>
                        {!isEditing ? (
                            <>
                                {displayEntity?.is_encrypted && (
                                    <div className="mb-4 flex items-center gap-2 p-2 bg-blue-50/50 dark:bg-blue-900/10 rounded border border-blue-100/50 dark:border-blue-900/30 text-blue-800 dark:text-blue-300 text-xs font-semibold w-fit">
                                        <span>🔒 Client-Side Encrypted</span>
                                    </div>
                                )}
                                {renderField('Display Name', displayEntity?.display)}
                                
                                {/* Tags - Show early for visibility */}
                                {displayEntity.tags && displayEntity.tags.length > 0 && (
                                    <div className="mb-4">
                                        <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                            Tags
                                        </h3>
                                        {renderField('', displayEntity.tags, true, false, true)}
                                    </div>
                                )}

                                {/* Description - Render as HTML */}
                                {displayEntity?.description && (
                                    <div className="mb-4">
                                        <h3 className="text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                            Description
                                        </h3>
                                        <div
                                            ref={descriptionRef}
                                            className="prose dark:prose-invert max-w-none text-gray-900 dark:text-gray-100 border border-gray-200 dark:border-gray-600 rounded-lg px-3 py-2"
                                            dangerouslySetInnerHTML={{ __html: processedDescription || displayEntity.description || '' }}
                                        />
                                    </div>
                                )}
                            </>
                        ) : (
                            <>
                                {/* Type selector for new entities only */}
                                {entity?.isNew && (
                                    <div className="mb-4">
                                        <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                            Type
                                        </label>
                                        <select
                                            value={editedEntity?.type || 'Person'}
                                            onChange={(e) => handleFieldChange('type', e.target.value)}
                                            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                        >
                                            <option value="Person">Person</option>
                                            <option value="Note">Note</option>
                                            <option value="Location">Location</option>
                                            <option value="Movie">Movie</option>
                                            <option value="Book">Book</option>
                                            <option value="Container">Container</option>
                                            <option value="Asset">Asset</option>
                                            <option value="Org">Org</option>
                                        </select>
                                    </div>
                                )}

                                {/* Secure Vault Lock Toggle */}
                                <div className="mb-4 flex items-center justify-between p-3 bg-blue-50 dark:bg-blue-900/20 rounded-lg border border-blue-200 dark:border-blue-800/50">
                                    <div className="flex flex-col">
                                        <span className="text-sm font-semibold text-gray-800 dark:text-gray-200 flex items-center gap-1.5">
                                            🔒 Secure Vault Lock
                                        </span>
                                        <span className="text-xs text-gray-500 dark:text-gray-400 font-normal">
                                            Encrypt all fields in-browser before sending to server
                                        </span>
                                    </div>
                                    <label className="relative inline-flex items-center cursor-pointer">
                                        <input
                                            type="checkbox"
                                            checked={editedEntity?.is_encrypted || false}
                                            onChange={(e) => {
                                                const checked = e.target.checked;
                                                handleFieldChange('is_encrypted', checked);
                                            }}
                                            className="sr-only peer"
                                        />
                                        <div className="w-11 h-6 bg-gray-200 peer-focus:outline-none peer-focus:ring-4 peer-focus:ring-blue-300 dark:peer-focus:ring-blue-800 rounded-full peer dark:bg-gray-700 peer-checked:after:translate-x-full peer-checked:after:border-white after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:border-gray-300 after:border after:rounded-full after:h-5 after:w-5 after:transition-all dark:border-gray-600 peer-checked:bg-blue-600"></div>
                                    </label>
                                </div>

                                {editedEntity?.is_encrypted && !hasKeys && (
                                    <div className="mb-4 p-3 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg border border-yellow-200 dark:border-yellow-800/50 space-y-2">
                                        <span className="text-xs font-semibold text-yellow-800 dark:text-yellow-200 block">
                                            ⚠️ Passphrase required to initialize encryption key
                                        </span>
                                        <div className="flex gap-2">
                                            <input
                                                type="password"
                                                placeholder="Enter passphrase to derive key"
                                                value={vaultPassphrase}
                                                onChange={(e) => setVaultPassphrase(e.target.value)}
                                                disabled={isInitializingKey}
                                                className="flex-1 px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                            />
                                            <button
                                                type="button"
                                                disabled={isInitializingKey || !vaultPassphrase.trim()}
                                                onClick={async () => {
                                                    setIsInitializingKey(true);
                                                    try {
                                                        await deriveKey(vaultPassphrase);
                                                        setVaultPassphrase('');
                                                    } catch (err) {
                                                        alert('Failed to derive key');
                                                    } finally {
                                                        setIsInitializingKey(false);
                                                    }
                                                }}
                                                className="px-3 py-1.5 text-sm font-semibold rounded-lg bg-yellow-600 hover:bg-yellow-700 text-white disabled:bg-gray-400"
                                            >
                                                {isInitializingKey ? 'Deriving...' : 'Initialize'}
                                            </button>
                                        </div>
                                    </div>
                                )}

                                {renderEditableField('Display Name', 'display', editedEntity?.display)}

                                {/* Tags Input */}
                                <div className="mb-4">
                                    <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                        Tags
                                    </label>
                                    <TagInput
                                        value={editedEntity?.tags || []}
                                        onChange={(tags) => handleFieldChange('tags', tags)}
                                        disabled={false}
                                    />
                                </div>

                                {/* Description - Rich Text Editor */}
                                <div className="mb-4">
                                    <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                        Description
                                    </label>
                                    <RichTextEditor
                                        value={editedEntity?.description || ''}
                                        onChange={(html) => handleFieldChange('description', html)}
                                        placeholder="Enter description..."
                                        isEncrypted={editedEntity?.is_encrypted}
                                        entityId={editedEntity?.id}
                                    />
                                </div>
                            </>
                        )}
                    </section>

                    {/* Person-specific fields */}
                    {displayEntity.type === 'Person' && (
                        <section>
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                Personal Details
                            </h3>
                            {!isEditing ? (
                                <>
                                    {renderField('First Name', displayEntity.first_name)}
                                    {renderField('Last Name', displayEntity.last_name)}
                                    {renderField('Date of Birth', displayEntity.dob)}
                                    {renderField('Gender', displayEntity.gender)}
                                    {renderField('Profession', displayEntity.profession)}
                                    {renderField('Emails', displayEntity.emails, true)}
                                    {renderField('Phones', displayEntity.phones, true)}
                                </>
                            ) : (
                                <>
                                    {renderEditableField('First Name', 'first_name', editedEntity?.first_name)}
                                    {renderEditableField('Last Name', 'last_name', editedEntity?.last_name)}
                                    {renderEditableField('Date of Birth', 'dob', editedEntity?.dob, 'date')}
                                    {renderEditableField('Gender', 'gender', editedEntity?.gender)}
                                    {renderEditableField('Profession', 'profession', editedEntity?.profession)}
                                    <div className="mb-4">
                                        <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                            Emails (comma-separated)
                                        </label>
                                        <input
                                            type="text"
                                            value={editedEntity?.emails?.join(', ') || ''}
                                            onChange={(e) => handleFieldChange('emails', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                                            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                        />
                                    </div>
                                    <div className="mb-4">
                                        <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                            Phones (comma-separated)
                                        </label>
                                        <input
                                            type="text"
                                            value={editedEntity?.phones?.join(', ') || ''}
                                            onChange={(e) => handleFieldChange('phones', e.target.value.split(',').map(s => s.trim()).filter(Boolean))}
                                            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                        />
                                    </div>
                                </>
                            )}
                        </section>
                    )}

                    {/* Note-specific fields */}
                    {displayEntity.type === 'Note' && (
                        <section>
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                Note Details
                            </h3>
                            {!isEditing ? (
                                <>
                                    {renderField('Date', displayEntity.date)}
                                </>
                            ) : (
                                <>
                                    {renderEditableField('Date', 'date', editedEntity?.date, 'date')}
                                </>
                            )}
                        </section>
                    )}

                    {/* Location-specific fields */}
                    {displayEntity.type === 'Location' && (
                        <section>
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                Address Details
                            </h3>
                            {!isEditing ? (
                                <>
                                    {renderField('Address Line 1', displayEntity.address1)}
                                    {renderField('Address Line 2', displayEntity.address2)}
                                    {renderField('City', displayEntity.city)}
                                    {renderField('State/Province', displayEntity.state)}
                                    {renderField('Postal Code', displayEntity.postal_code)}
                                    {renderField('Country', displayEntity.country)}
                                </>
                            ) : (
                                <>
                                    {renderEditableField('Address Line 1', 'address1', editedEntity?.address1)}
                                    {renderEditableField('Address Line 2', 'address2', editedEntity?.address2)}
                                    {renderEditableField('City', 'city', editedEntity?.city)}
                                    {renderEditableField('State/Province', 'state', editedEntity?.state)}
                                    {renderEditableField('Postal Code', 'postal_code', editedEntity?.postal_code)}
                                    {renderEditableField('Country', 'country', editedEntity?.country)}
                                </>
                            )}
                        </section>
                    )}

                    {/* Movie-specific fields */}
                    {displayEntity.type === 'Movie' && (
                        <section>
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                Movie Details
                            </h3>
                            {!isEditing ? (
                                <>
                                    {renderField('Year', displayEntity.year)}
                                    {renderField('Language', displayEntity.language)}
                                    {renderField('Country', displayEntity.country)}
                                </>
                            ) : (
                                <>
                                    {renderEditableField('Year', 'year', editedEntity?.year, 'number')}
                                    {renderEditableField('Language', 'language', editedEntity?.language)}
                                    {renderEditableField('Country', 'country', editedEntity?.country)}
                                </>
                            )}
                        </section>
                    )}

                    {/* Book-specific fields */}
                    {displayEntity.type === 'Book' && (
                        <section>
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                Book Details
                            </h3>
                            {!isEditing ? (
                                <>
                                    {renderField('Year', displayEntity.year)}
                                    {renderField('Language', displayEntity.language)}
                                    {renderField('Country', displayEntity.country)}
                                    {renderField('Summary', displayEntity.summary)}
                                </>
                            ) : (
                                <>
                                    {renderEditableField('Year', 'year', editedEntity?.year, 'number')}
                                    {renderEditableField('Language', 'language', editedEntity?.language)}
                                    {renderEditableField('Country', 'country', editedEntity?.country)}
                                    <div className="mb-4">
                                        <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                            Summary
                                        </label>
                                        <textarea
                                            value={editedEntity?.summary || ''}
                                            onChange={(e) => handleFieldChange('summary', e.target.value)}
                                            rows={4}
                                            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                            placeholder="Enter book summary..."
                                        />
                                    </div>
                                </>
                            )}
                        </section>
                    )}

                    {/* Asset-specific fields */}
                    {displayEntity.type === 'Asset' && (
                        <section>
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                Asset Details
                            </h3>
                            {!isEditing ? (
                                <>
                                    {renderField('Value', displayEntity.value)}
                                    {renderField('Acquired On', displayEntity.acquired_on)}
                                </>
                            ) : (
                                <>
                                    {renderEditableField('Value', 'value', editedEntity?.value, 'number')}
                                    {renderEditableField('Acquired On', 'acquired_on', editedEntity?.acquired_on)}
                                </>
                            )}
                        </section>
                    )}

                    {/* Org-specific fields */}
                    {displayEntity.type === 'Org' && (
                        <section>
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                Organization Details
                            </h3>
                            {!isEditing ? (
                                <>
                                    {renderField('Name', displayEntity.name)}
                                    {renderField('Kind', displayEntity.kind)}
                                </>
                            ) : (
                                <>
                                    {renderEditableField('Name', 'name', editedEntity?.name)}
                                    <div className="mb-4">
                                        <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                            Kind
                                        </label>
                                        <select
                                            value={editedEntity?.kind || 'Unspecified'}
                                            onChange={(e) => handleFieldChange('kind', e.target.value)}
                                            className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100"
                                        >
                                            <option value="School">School</option>
                                            <option value="University">University</option>
                                            <option value="Company">Company</option>
                                            <option value="NonProfit">NonProfit</option>
                                            <option value="Club">Club</option>
                                            <option value="Unspecified">Unspecified</option>
                                        </select>
                                    </div>
                                </>
                            )}
                        </section>
                    )}

                    {/* Locations */}
                    {(displayEntity.locations?.length > 0 || isEditing) && (
                        <section>
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                Locations
                            </h3>

                            {(editedEntity?.locations?.length > 0 || displayEntity.locations?.length > 0) && (
                                <div className="mb-4 space-y-4">
                                    {(isEditing ? editedEntity.locations : displayEntity.locations)?.map((loc, idx) => {
                                        const name = loc?.name || '';
                                        const lat = loc?.latitude ?? loc?.lat;
                                        const lon = loc?.longitude ?? loc?.lon;
                                        const elev = loc?.elevation ?? loc?.altitude ?? loc?.elev;
                                        const mapsUrl = getGoogleMapsUrl(loc);
                                        const hasCoords = lat != null && lon != null;
                                        const hasName = !!name.trim();
                                        const isLoading = geocodeLoading?.idx === idx;
                                        const totalLocs = (isEditing ? editedEntity.locations : displayEntity.locations).length;

                                        return isEditing ? (
                                            <div key={idx} className="p-3 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600">
                                                <div className="flex items-center justify-between mb-2">
                                                    <span className="text-sm font-medium text-gray-600 dark:text-gray-400">Location {idx + 1}</span>
                                                    <div className="flex gap-1">
                                                        <button onClick={() => moveLocationUp(idx)} disabled={idx === 0} className="p-1 text-gray-600 dark:text-gray-300 hover:text-blue-600 disabled:opacity-30" title="Move up">↑</button>
                                                        <button onClick={() => moveLocationDown(idx)} disabled={idx >= totalLocs - 1} className="p-1 text-gray-600 dark:text-gray-300 hover:text-blue-600 disabled:opacity-30" title="Move down">↓</button>
                                                        <button onClick={() => removeLocation(idx)} className="p-1 text-red-600 hover:text-red-800" title="Remove">✕</button>
                                                    </div>
                                                </div>
                                                <div className="grid gap-2">
                                                    <div>
                                                        <label className="block text-xs text-gray-500 dark:text-gray-400 mb-0.5">Name</label>
                                                        <div className="flex gap-2">
                                                            <input
                                                                type="text"
                                                                value={name}
                                                                onChange={(e) => handleLocationChange(idx, 'name', e.target.value)}
                                                                placeholder="Place name"
                                                                className="flex-1 px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                            />
                                                            {hasName && (
                                                                <button
                                                                    onClick={() => handleLookupCoords(idx)}
                                                                    disabled={isLoading}
                                                                    className="px-2 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                                                                >
                                                                    {geocodeLoading?.idx === idx && geocodeLoading?.type === 'forward' ? '…' : 'Look up coords'}
                                                                </button>
                                                            )}
                                                        </div>
                                                    </div>
                                                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2">
                                                        <div>
                                                            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-0.5">Latitude</label>
                                                            <input
                                                                type="number"
                                                                step="any"
                                                                value={lat ?? ''}
                                                                onChange={(e) => handleLocationChange(idx, 'latitude', e.target.value ? parseFloat(e.target.value) : null)}
                                                                placeholder="Lat"
                                                                className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                            />
                                                        </div>
                                                        <div>
                                                            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-0.5">Longitude</label>
                                                            <input
                                                                type="number"
                                                                step="any"
                                                                value={lon ?? ''}
                                                                onChange={(e) => handleLocationChange(idx, 'longitude', e.target.value ? parseFloat(e.target.value) : null)}
                                                                placeholder="Lon"
                                                                className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                            />
                                                        </div>
                                                        <div>
                                                            <label className="block text-xs text-gray-500 dark:text-gray-400 mb-0.5">Elevation (m)</label>
                                                            <input
                                                                type="number"
                                                                step="any"
                                                                value={elev ?? ''}
                                                                onChange={(e) => handleLocationChange(idx, 'elevation', e.target.value ? parseFloat(e.target.value) : null)}
                                                                placeholder="m"
                                                                className="w-full px-2 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                            />
                                                        </div>
                                                        {hasCoords && (
                                                            <div className="flex items-end">
                                                                <button
                                                                    onClick={() => handleLookupName(idx)}
                                                                    disabled={isLoading}
                                                                    className="px-2 py-1.5 text-sm bg-blue-600 text-white rounded hover:bg-blue-700 disabled:opacity-50"
                                                                >
                                                                    {geocodeLoading?.idx === idx && geocodeLoading?.type === 'reverse' ? '…' : 'Lookup name'}
                                                                </button>
                                                            </div>
                                                        )}
                                                    </div>
                                                </div>
                                            </div>
                                        ) : (
                                            /* Display mode: name only; lat/long/altitude shown only in edit */
                                            <div key={idx} className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700 rounded">
                                                <span className="text-gray-900 dark:text-gray-100">{name || '(Unnamed)'}</span>
                                                {mapsUrl && (
                                                    <a
                                                        href={mapsUrl}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="px-2 py-1 text-sm bg-blue-600 text-white rounded hover:bg-blue-700"
                                                    >
                                                        Map
                                                    </a>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}

                            {isEditing && (
                                <button
                                    onClick={addLocation}
                                    className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 text-sm"
                                >
                                    + Add Location
                                </button>
                            )}
                        </section>
                    )}

                    {/* Photos */}
                    {(displayEntity.photos?.length > 0 || newPhotos.length > 0 || isEditing) && (
                        <section
                            onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); if (isEditing) setIsDraggingPhotos(true); }}
                            onDragLeave={(e) => { e.preventDefault(); if (!e.currentTarget.contains(e.relatedTarget)) setIsDraggingPhotos(false); }}
                            onDrop={handlePhotoDrop}
                            className={isDraggingPhotos ? 'rounded-lg border-2 border-blue-500 bg-blue-50 dark:bg-blue-900/20 p-2 -m-2' : ''}
                        >
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                Photos
                            </h3>

                            {/* Existing Photos */}
                            {(editedEntity?.photos?.length > 0 || displayEntity.photos?.length > 0) && (
                                <div className={`mb-4 ${isEditing ? 'grid grid-cols-2 gap-2' : 'grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3'}`}>
                                    {(isEditing ? editedEntity.photos : displayEntity.photos)?.map((photo, idx) => {
                                        // Handle both old format (string) and new format (object)
                                        const photoUrl = typeof photo === 'string' ? photo : photo.url;
                                        const thumbnailUrl = typeof photo === 'string' ? photo : (photo.thumbnail_url || photo.url);
                                        const photoCaption = typeof photo === 'string' ? '' : (photo.caption || '');
                                        const photoFilename = typeof photo === 'string' ? photo.split('/').pop() : (photo.filename || photo.url.split('/').pop());
                                        const displayCaption = photoCaption || photoFilename;
                                        const totalPhotos = (isEditing ? editedEntity.photos : displayEntity.photos).length;

                                        return isEditing ? (
                                            // Edit Mode: Larger thumbnails with controls
                                            <div key={idx} className="relative group flex flex-col bg-gray-50 dark:bg-gray-800 p-2 rounded border border-gray-200 dark:border-gray-700">
                                                <div className="w-full h-32 md:h-40 flex items-center justify-center bg-gray-100 dark:bg-gray-900 rounded overflow-hidden">
                                                    {editedEntity.is_encrypted ? (
                                                        <DecryptedImage
                                                            src={getMediaUrl(thumbnailUrl)}
                                                            alt={displayCaption}
                                                            className="max-w-full max-h-full object-contain cursor-pointer hover:opacity-80 transition"
                                                            onClick={async () => {
                                                                try {
                                                                    const decryptedUrls = await Promise.all(
                                                                        editedEntity.photos.map(async (p) => {
                                                                            const url = typeof p === 'string' ? p : p.url;
                                                                            const fullUrl = getMediaUrl(url);
                                                                            const response = await fetch(fullUrl);
                                                                            const encryptedBlob = await response.blob();
                                                                            
                                                                            let mimeType = 'image/jpeg';
                                                                            if (url.toLowerCase().includes('.png')) mimeType = 'image/png';
                                                                            if (url.toLowerCase().includes('.gif')) mimeType = 'image/gif';
                                                                            if (url.toLowerCase().includes('.webp')) mimeType = 'image/webp';
                                                                            
                                                                            const decryptedBlob = await decryptBlob(encryptedBlob, mimeType, editedEntity._decryption_key || encryptionKeys[encryptionKeys.length - 1]);
                                                                            return URL.createObjectURL(decryptedBlob);
                                                                        })
                                                                    );
                                                                    setLightboxImages(decryptedUrls);
                                                                    setLightboxIndex(idx);
                                                                } catch (err) {
                                                                    console.error('Failed to decrypt photos for lightbox:', err);
                                                                    alert('Failed to decrypt photos.');
                                                                }
                                                            }}
                                                            title={displayCaption}
                                                            decryptionKey={editedEntity._decryption_key || encryptionKeys[encryptionKeys.length - 1]}
                                                        />
                                                    ) : (
                                                        <img
                                                            src={getMediaUrl(thumbnailUrl)}
                                                            alt={displayCaption}
                                                            className="max-w-full max-h-full object-contain cursor-pointer hover:opacity-80 transition"
                                                            onClick={() => {
                                                                const allPhotos = editedEntity.photos.map(p => {
                                                                    const url = typeof p === 'string' ? p : p.url;
                                                                    return getMediaUrl(url);
                                                                });
                                                                setLightboxImages(allPhotos);
                                                                setLightboxIndex(idx);
                                                            }}
                                                            title={displayCaption}
                                                        />
                                                    )}
                                                </div>
                                                {/* Delete Button */}
                                                <button
                                                    onClick={(e) => {
                                                        e.stopPropagation();
                                                        handleDeletePhoto(photo);
                                                    }}
                                                    className="absolute top-1 right-1 p-1 bg-red-600 text-white rounded-full hover:bg-red-700 shadow-lg"
                                                    title="Delete photo"
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                    </svg>
                                                </button>

                                                {/* Reorder Buttons */}
                                                <div className="absolute top-1 left-1 flex flex-col gap-1">
                                                    {idx > 0 && (
                                                        <button
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                movePhotoUp(idx);
                                                            }}
                                                            className="p-1 bg-blue-600 text-white rounded hover:bg-blue-700 shadow-lg"
                                                            title="Move up"
                                                        >
                                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                                                            </svg>
                                                        </button>
                                                    )}
                                                    {idx < totalPhotos - 1 && (
                                                        <button
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                movePhotoDown(idx);
                                                            }}
                                                            className="p-1 bg-blue-600 text-white rounded hover:bg-blue-700 shadow-lg"
                                                            title="Move down"
                                                        >
                                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                                            </svg>
                                                        </button>
                                                    )}
                                                </div>

                                                {/* Caption Input */}
                                                <div className="mt-1">
                                                    <input
                                                        type="text"
                                                        value={photoCaption}
                                                        onChange={(e) => {
                                                            const newPhotos = [...editedEntity.photos];
                                                            if (typeof newPhotos[idx] === 'string') {
                                                                // Convert string to object format
                                                                newPhotos[idx] = {
                                                                    url: newPhotos[idx],
                                                                    caption: e.target.value
                                                                };
                                                            } else {
                                                                newPhotos[idx] = {
                                                                    ...newPhotos[idx],
                                                                    caption: e.target.value
                                                                };
                                                            }
                                                            setEditedEntity(prev => ({
                                                                ...prev,
                                                                photos: newPhotos
                                                            }));
                                                        }}
                                                        placeholder={photoFilename}
                                                        className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                    />
                                                </div>
                                            </div>
                                        ) : (
                                            // Detail Mode: Grid item with square thumbnail
                                            <div key={idx} className="flex flex-col items-center gap-1 p-2 bg-gray-50 dark:bg-gray-700 rounded">
                                                {displayEntity.is_encrypted ? (
                                                    <DecryptedImage
                                                        src={getMediaUrl(thumbnailUrl)}
                                                        alt={displayCaption}
                                                        className="w-full aspect-square object-cover rounded cursor-pointer hover:opacity-80 transition"
                                                        onClick={async () => {
                                                            try {
                                                                const decryptedUrls = await Promise.all(
                                                                    displayEntity.photos.map(async (p) => {
                                                                        const url = typeof p === 'string' ? p : p.url;
                                                                        const fullUrl = getMediaUrl(url);
                                                                        const response = await fetch(fullUrl);
                                                                        const encryptedBlob = await response.blob();
                                                                        
                                                                        let mimeType = 'image/jpeg';
                                                                        if (url.toLowerCase().includes('.png')) mimeType = 'image/png';
                                                                        if (url.toLowerCase().includes('.gif')) mimeType = 'image/gif';
                                                                        if (url.toLowerCase().includes('.webp')) mimeType = 'image/webp';
                                                                        
                                                                        const decryptedBlob = await decryptBlob(encryptedBlob, mimeType, displayEntity._decryption_key);
                                                                        return URL.createObjectURL(decryptedBlob);
                                                                    })
                                                                );
                                                                setLightboxImages(decryptedUrls);
                                                                setLightboxIndex(idx);
                                                            } catch (err) {
                                                                console.error('Failed to decrypt photos for lightbox:', err);
                                                                alert('Failed to decrypt photos. Is the vault unlocked?');
                                                            }
                                                        }}
                                                        title={displayCaption}
                                                        decryptionKey={displayEntity._decryption_key}
                                                    />
                                                ) : (
                                                    <img
                                                        src={getMediaUrl(thumbnailUrl)}
                                                        alt={displayCaption}
                                                        className="w-full aspect-square object-cover rounded cursor-pointer hover:opacity-80 transition"
                                                        onClick={() => {
                                                            const allPhotos = displayEntity.photos.map(p => {
                                                                const url = typeof p === 'string' ? p : p.url;
                                                                return getMediaUrl(url);
                                                            });
                                                            setLightboxImages(allPhotos);
                                                            setLightboxIndex(idx);
                                                        }}
                                                        title={displayCaption}
                                                    />
                                                )}
                                                <span className="text-xs text-gray-700 dark:text-gray-300 text-center w-full truncate px-1" title={displayCaption}>
                                                    {displayCaption}
                                                </span>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}

                            {/* New Photos Preview */}
                            {isEditing && newPhotos.length > 0 && (
                                <div className="mb-4">
                                    <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">New Photos:</p>
                                    <div className="grid grid-cols-2 gap-2">
                                        {newPhotos.map((file, idx) => (
                                            <div key={idx} className="relative flex flex-col bg-gray-50 dark:bg-gray-800 p-2 rounded border border-gray-200 dark:border-gray-700">
                                                <div className="w-full h-32 md:h-40 flex items-center justify-center bg-gray-100 dark:bg-gray-900 rounded overflow-hidden">
                                                    <img
                                                        src={URL.createObjectURL(file)}
                                                        alt={`New photo ${idx + 1}`}
                                                        className="max-w-full max-h-full object-contain"
                                                    />
                                                </div>
                                                <button
                                                    onClick={() => handleDeleteNewPhoto(idx)}
                                                    className="absolute top-1 right-1 p-1 bg-red-600 text-white rounded-full hover:bg-red-700"
                                                    title="Remove photo"
                                                >
                                                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                    </svg>
                                                </button>
                                                {/* Caption Input */}
                                                <div className="mt-1">
                                                    <input
                                                        type="text"
                                                        value={file.caption || ''}
                                                        onChange={(e) => {
                                                            const updatedPhotos = [...newPhotos];
                                                            updatedPhotos[idx].caption = e.target.value;
                                                            setNewPhotos(updatedPhotos);
                                                        }}
                                                        placeholder={file.name}
                                                        className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                    />
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Add Photos Button + Drop Zone */}
                            {isEditing && (
                                <div className="rounded-lg border-2 border-dashed border-gray-300 dark:border-gray-600 p-4 text-center text-sm text-gray-500 dark:text-gray-400">
                                    <p className="mb-2">Drop images here (files or from a webpage)</p>
                                    <label className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer">
                                        <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                        </svg>
                                        Add Photos
                                        <input
                                            type="file"
                                            accept="image/*"
                                            multiple
                                            onChange={handlePhotoSelect}
                                            className="hidden"
                                        />
                                    </label>
                                </div>
                            )}
                        </section>
                    )}

                    {/* Attachments */}
                    {(displayEntity.attachments?.length > 0 || newAttachments.length > 0 || isEditing) && (
                        <section
                            onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); if (isEditing) setIsDraggingAttachments(true); }}
                            onDragLeave={(e) => { e.preventDefault(); if (!e.currentTarget.contains(e.relatedTarget)) setIsDraggingAttachments(false); }}
                            onDrop={handleAttachmentDrop}
                            className={isDraggingAttachments ? 'rounded-lg border-2 border-blue-500 bg-blue-50 dark:bg-blue-900/20 p-2 -m-2' : ''}
                        >
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                Attachments
                            </h3>

                            {/* Existing Attachments */}
                            {(editedEntity?.attachments?.length > 0 || displayEntity.attachments?.length > 0) && (
                                <div className={`mb-4 ${isEditing ? 'space-y-2' : 'grid grid-cols-3 sm:grid-cols-4 md:grid-cols-5 lg:grid-cols-6 gap-3'}`}>
                                    {(isEditing ? editedEntity.attachments : displayEntity.attachments)?.map((attachment, idx) => {
                                        // Handle both old format (string) and new format (object)
                                        const attachmentUrl = typeof attachment === 'string' ? attachment : attachment.url;
                                        const thumbnailUrl = typeof attachment === 'string' ? null : (attachment.thumbnail_url || attachment.preview_url);
                                        const previewUrl = typeof attachment === 'string' ? null : attachment.preview_url;
                                        // Use original filename if available, otherwise extract from URL
                                        const filename = typeof attachment === 'string'
                                            ? attachment.split('/').pop()
                                            : (attachment.filename || attachment.url.split('/').pop());
                                        const attachmentCaption = typeof attachment === 'string' ? '' : (attachment.caption || '');
                                        // Display caption if available, otherwise show filename
                                        const displayName = attachmentCaption || filename;
                                        const totalAttachments = (isEditing ? editedEntity.attachments : displayEntity.attachments).length;

                                        return isEditing ? (
                                            // Edit Mode: Row layout with controls
                                            <div key={idx} className="flex items-center gap-3 p-2 bg-gray-50 dark:bg-gray-700 rounded">
                                                {/* Reorder Buttons */}
                                                <div className="flex flex-col gap-1 flex-shrink-0">
                                                    <button
                                                        onClick={() => moveAttachmentUp(idx)}
                                                        disabled={idx === 0}
                                                        className="p-1 text-gray-600 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 disabled:opacity-30 disabled:cursor-not-allowed"
                                                        title="Move up"
                                                    >
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" />
                                                        </svg>
                                                    </button>
                                                    <button
                                                        onClick={() => moveAttachmentDown(idx)}
                                                        disabled={idx === totalAttachments - 1}
                                                        className="p-1 text-gray-600 dark:text-gray-300 hover:text-blue-600 dark:hover:text-blue-400 disabled:opacity-30 disabled:cursor-not-allowed"
                                                        title="Move down"
                                                    >
                                                        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                                                        </svg>
                                                    </button>
                                                </div>

                                                {/* Thumbnail Preview */}
                                                {thumbnailUrl && (
                                                    editedEntity.is_encrypted ? (
                                                        <DecryptedImage
                                                            src={getMediaUrl(thumbnailUrl)}
                                                            alt={filename}
                                                            className="w-16 h-16 object-cover rounded cursor-pointer hover:opacity-80 transition flex-shrink-0"
                                                            onClick={async (e) => {
                                                                e.preventDefault();
                                                                e.stopPropagation();
                                                                try {
                                                                    const url = previewUrl || attachmentUrl;
                                                                    const fullUrl = getMediaUrl(url);
                                                                    const response = await fetch(fullUrl);
                                                                    const encryptedBlob = await response.blob();
                                                                    
                                                                    let mimeType = 'image/jpeg';
                                                                    if (url.toLowerCase().includes('.png')) mimeType = 'image/png';
                                                                    if (url.toLowerCase().includes('.gif')) mimeType = 'image/gif';
                                                                    if (url.toLowerCase().includes('.webp')) mimeType = 'image/webp';
                                                                    
                                                                    const decryptedBlob = await decryptBlob(encryptedBlob, mimeType, editedEntity._decryption_key || encryptionKeys[encryptionKeys.length - 1]);
                                                                    const blobUrl = URL.createObjectURL(decryptedBlob);
                                                                    setLightboxImages([blobUrl]);
                                                                    setLightboxIndex(0);
                                                                } catch (err) {
                                                                    console.error('Failed to decrypt attachment preview:', err);
                                                                }
                                                            }}
                                                            title="Click to view preview"
                                                            decryptionKey={editedEntity._decryption_key || encryptionKeys[encryptionKeys.length - 1]}
                                                        />
                                                    ) : (
                                                        <img
                                                            src={getMediaUrl(thumbnailUrl)}
                                                            alt={filename}
                                                            className="w-16 h-16 object-cover rounded cursor-pointer hover:opacity-80 transition flex-shrink-0"
                                                            onClick={(e) => {
                                                                e.preventDefault();
                                                                e.stopPropagation();
                                                                setLightboxImages([getMediaUrl(previewUrl || attachmentUrl)]);
                                                                setLightboxIndex(0);
                                                            }}
                                                            title="Click to view preview"
                                                        />
                                                    )
                                                )}

                                                {/* File Info */}
                                                <div className="flex-1 min-w-0">
                                                    {editedEntity.is_encrypted ? (
                                                        <button
                                                            onClick={(e) => {
                                                                e.preventDefault();
                                                                handleAttachmentClick(attachmentUrl, filename, editedEntity._decryption_key || encryptionKeys[encryptionKeys.length - 1]);
                                                            }}
                                                            className="text-blue-600 dark:text-blue-400 hover:underline truncate block text-left bg-transparent border-none p-0 cursor-pointer font-medium"
                                                            title={`Decrypt and Download ${filename}`}
                                                        >
                                                            {displayName}
                                                        </button>
                                                    ) : (
                                                        <a
                                                            href={getMediaUrl(attachmentUrl)}
                                                            target="_blank"
                                                            rel="noopener noreferrer"
                                                            className="text-blue-600 dark:text-blue-400 hover:underline truncate block"
                                                            title={`Download ${filename}`}
                                                        >
                                                            {displayName}
                                                        </a>
                                                    )}
                                                    {/* Caption Input */}
                                                    <input
                                                        type="text"
                                                        value={attachmentCaption}
                                                        onChange={(e) => {
                                                            const newAttachments = [...editedEntity.attachments];
                                                            if (typeof newAttachments[idx] === 'string') {
                                                                // Convert string to object format
                                                                newAttachments[idx] = {
                                                                    url: newAttachments[idx],
                                                                    caption: e.target.value
                                                                };
                                                            } else {
                                                                newAttachments[idx] = {
                                                                    ...newAttachments[idx],
                                                                    caption: e.target.value
                                                                };
                                                            }
                                                            setEditedEntity(prev => ({
                                                                ...prev,
                                                                attachments: newAttachments
                                                            }));
                                                        }}
                                                        placeholder={filename}
                                                        className="w-full mt-1 px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                    />
                                                </div>

                                                {/* Delete Button */}
                                                <button
                                                    onClick={() => handleDeleteAttachment(attachment)}
                                                    className="p-1 text-red-600 hover:text-red-700 flex-shrink-0"
                                                    title="Delete attachment"
                                                >
                                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                    </svg>
                                                </button>
                                            </div>
                                        ) : (
                                            // Detail Mode: Grid item layout
                                            <div key={idx} className="flex flex-col items-center gap-1 p-2 bg-gray-50 dark:bg-gray-700 rounded">
                                                {thumbnailUrl ? (
                                                    <>
                                                        {displayEntity.is_encrypted ? (
                                                            <DecryptedImage
                                                                src={getMediaUrl(thumbnailUrl)}
                                                                alt={filename}
                                                                className="w-full aspect-square object-cover rounded cursor-pointer hover:opacity-80 transition"
                                                                onClick={async (e) => {
                                                                    e.preventDefault();
                                                                    e.stopPropagation();
                                                                    try {
                                                                        const url = previewUrl || attachmentUrl;
                                                                        const fullUrl = getMediaUrl(url);
                                                                        const response = await fetch(fullUrl);
                                                                        const encryptedBlob = await response.blob();
                                                                        
                                                                        let mimeType = 'image/jpeg';
                                                                        if (url.toLowerCase().includes('.png')) mimeType = 'image/png';
                                                                        if (url.toLowerCase().includes('.gif')) mimeType = 'image/gif';
                                                                        if (url.toLowerCase().includes('.webp')) mimeType = 'image/webp';
                                                                        
                                                                        const decryptedBlob = await decryptBlob(encryptedBlob, mimeType, displayEntity._decryption_key);
                                                                        const blobUrl = URL.createObjectURL(decryptedBlob);
                                                                        setLightboxImages([blobUrl]);
                                                                        setLightboxIndex(0);
                                                                    } catch (err) {
                                                                        console.error('Failed to decrypt attachment preview:', err);
                                                                    }
                                                                }}
                                                                title="Click to view preview"
                                                                decryptionKey={displayEntity._decryption_key}
                                                            />
                                                        ) : (
                                                            <img
                                                                src={getMediaUrl(thumbnailUrl)}
                                                                alt={filename}
                                                                className="w-full aspect-square object-cover rounded cursor-pointer hover:opacity-80 transition"
                                                                onClick={(e) => {
                                                                    e.preventDefault();
                                                                    e.stopPropagation();
                                                                    setLightboxImages([getMediaUrl(previewUrl || attachmentUrl)]);
                                                                    setLightboxIndex(0);
                                                                }}
                                                                title="Click to view preview"
                                                            />
                                                        )}
                                                        {displayEntity.is_encrypted ? (
                                                            <button
                                                                onClick={(e) => {
                                                                    e.preventDefault();
                                                                    handleAttachmentClick(attachmentUrl, filename, displayEntity._decryption_key);
                                                                }}
                                                                className="text-xs text-blue-600 dark:text-blue-400 hover:underline text-center w-full truncate px-1 bg-transparent border-none p-0 cursor-pointer font-medium"
                                                                title={displayName}
                                                            >
                                                                {displayName}
                                                            </button>
                                                        ) : (
                                                            <a
                                                                href={getMediaUrl(attachmentUrl)}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="text-xs text-blue-600 dark:text-blue-400 hover:underline text-center w-full truncate px-1"
                                                                title={displayName}
                                                            >
                                                                {displayName}
                                                            </a>
                                                        )}
                                                    </>
                                                ) : (
                                                    // No thumbnail - show file icon and name
                                                    <>
                                                        <div className="w-full aspect-square flex items-center justify-center bg-gray-200 dark:bg-gray-600 rounded">
                                                            <svg className="w-12 h-12 text-gray-400 dark:text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                                                            </svg>
                                                        </div>
                                                        {displayEntity.is_encrypted ? (
                                                            <button
                                                                onClick={(e) => {
                                                                    e.preventDefault();
                                                                    handleAttachmentClick(attachmentUrl, filename, displayEntity._decryption_key);
                                                                }}
                                                                className="text-xs text-blue-600 dark:text-blue-400 hover:underline text-center w-full truncate px-1 bg-transparent border-none p-0 cursor-pointer font-medium"
                                                                title={displayName}
                                                            >
                                                                {displayName}
                                                            </button>
                                                        ) : (
                                                            <a
                                                                href={getMediaUrl(attachmentUrl)}
                                                                target="_blank"
                                                                rel="noopener noreferrer"
                                                                className="text-xs text-blue-600 dark:text-blue-400 hover:underline text-center w-full truncate px-1"
                                                                title={displayName}
                                                            >
                                                                {displayName}
                                                            </a>
                                                        )}
                                                    </>
                                                )}
                                            </div>
                                        );
                                    })}
                                </div>
                            )}

                            {/* New Attachments Preview */}
                            {isEditing && newAttachments.length > 0 && (
                                <div className="mb-4">
                                    <p className="text-sm font-medium text-gray-600 dark:text-gray-400 mb-2">New Attachments:</p>
                                    <div className="space-y-2">
                                        {newAttachments.map((file, idx) => (
                                            <div key={idx} className="p-2 bg-blue-50 dark:bg-blue-900 rounded">
                                                <div className="flex items-center justify-between mb-1">
                                                    <span className="text-gray-900 dark:text-gray-100 truncate flex-1">
                                                        {file.name}
                                                    </span>
                                                    <button
                                                        onClick={() => handleDeleteNewAttachment(idx)}
                                                        className="ml-2 p-1 text-red-600 hover:text-red-700 flex-shrink-0"
                                                        title="Remove attachment"
                                                    >
                                                        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                        </svg>
                                                    </button>
                                                </div>
                                                {/* Caption Input */}
                                                <input
                                                    type="text"
                                                    value={file.caption || ''}
                                                    onChange={(e) => {
                                                        const updatedAttachments = [...newAttachments];
                                                        updatedAttachments[idx].caption = e.target.value;
                                                        setNewAttachments(updatedAttachments);
                                                    }}
                                                    placeholder="Add caption (optional)"
                                                    className="w-full px-2 py-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                />
                                            </div>
                                        ))}
                                    </div>
                                </div>
                            )}

                            {/* Add Attachments Button + Drop Zone */}
                            {isEditing && (
                                <div className="rounded-lg border-2 border-dashed border-gray-300 dark:border-gray-600 p-4 text-center text-sm text-gray-500 dark:text-gray-400">
                                    <p className="mb-2">Drop files here (files or from a webpage)</p>
                                    <label className="inline-flex items-center px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 cursor-pointer">
                                        <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
                                        </svg>
                                        Add Attachments
                                        <input
                                            type="file"
                                            multiple
                                            onChange={handleAttachmentSelect}
                                            className="hidden"
                                        />
                                    </label>
                                </div>
                            )}
                        </section>
                    )}

                    {/* URLs */}
                    {(displayEntity.urls?.length > 0 || isEditing) && (
                        <section>
                            <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                URLs
                            </h3>

                            {/* Existing URLs */}
                            {(editedEntity?.urls?.length > 0 || displayEntity.urls?.length > 0) && (
                                <div className={`mb-4 ${isEditing ? 'space-y-2' : 'grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3'}`}>
                                    {(isEditing ? editedEntity.urls : displayEntity.urls)?.map((urlItem, idx) => {
                                        // Handle both old format (string) and new format (object)
                                        const url = typeof urlItem === 'string' ? urlItem : urlItem.url;
                                        const urlCaption = typeof urlItem === 'string' ? '' : (urlItem.caption || '');
                                        // Display caption if available, otherwise show URL
                                        const displayText = urlCaption || url;
                                        // Shorten display text if necessary
                                        const shortenedText = displayText.length > 40 ? displayText.substring(0, 37) + '...' : displayText;

                                        return isEditing ? (
                                            // Edit Mode: Row layout with controls
                                            <div key={idx} className="flex items-center gap-3 p-2 bg-gray-50 dark:bg-gray-700 rounded">
                                                {/* URL Link */}
                                                <div className="flex-1 min-w-0">
                                                    <a
                                                        href={url}
                                                        target="_blank"
                                                        rel="noopener noreferrer"
                                                        className="text-blue-600 dark:text-blue-400 hover:underline truncate block"
                                                        title={url}
                                                    >
                                                        {shortenedText}
                                                    </a>
                                                    {/* Caption Input */}
                                                    <input
                                                        type="text"
                                                        value={urlCaption}
                                                        onChange={(e) => {
                                                            const updatedUrls = [...editedEntity.urls];
                                                            if (typeof updatedUrls[idx] === 'string') {
                                                                updatedUrls[idx] = { url: updatedUrls[idx], caption: e.target.value };
                                                            } else {
                                                                updatedUrls[idx] = { ...updatedUrls[idx], caption: e.target.value };
                                                            }
                                                            setEditedEntity({ ...editedEntity, urls: updatedUrls });
                                                        }}
                                                        placeholder="Add caption (optional)"
                                                        className="w-full px-2 py-1 mt-1 text-sm border border-gray-300 dark:border-gray-600 rounded bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                    />
                                                </div>

                                                {/* Delete Button */}
                                                <button
                                                    onClick={() => {
                                                        const updatedUrls = editedEntity.urls.filter((_, i) => i !== idx);
                                                        setEditedEntity({ ...editedEntity, urls: updatedUrls });
                                                    }}
                                                    className="p-1 text-red-600 dark:text-red-400 hover:text-red-800 dark:hover:text-red-300 flex-shrink-0"
                                                    title="Remove URL"
                                                >
                                                    <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                    </svg>
                                                </button>
                                            </div>
                                        ) : (
                                            // Detail Mode: Grid item
                                            <div key={idx} className="flex flex-col items-start gap-1 p-2 bg-gray-50 dark:bg-gray-700 rounded">
                                                <a
                                                    href={url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="text-blue-600 dark:text-blue-400 hover:underline text-sm truncate w-full"
                                                    title={displayText}
                                                >
                                                    {shortenedText}
                                                </a>
                                            </div>
                                        );
                                    })}
                                </div>
                            )}

                            {/* Add URL Button */}
                            {isEditing && (
                                <div className="flex gap-2">
                                    <input
                                        type="url"
                                        placeholder="Enter URL"
                                        className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                        onKeyPress={(e) => {
                                            if (e.key === 'Enter' && e.target.value.trim()) {
                                                const newUrl = { url: e.target.value.trim(), caption: '' };
                                                setEditedEntity({
                                                    ...editedEntity,
                                                    urls: [...(editedEntity.urls || []), newUrl]
                                                });
                                                e.target.value = '';
                                            }
                                        }}
                                    />
                                    <button
                                        onClick={(e) => {
                                            const input = e.target.previousElementSibling;
                                            if (input.value.trim()) {
                                                const newUrl = { url: input.value.trim(), caption: '' };
                                                setEditedEntity({
                                                    ...editedEntity,
                                                    urls: [...(editedEntity.urls || []), newUrl]
                                                });
                                                input.value = '';
                                            }
                                        }}
                                        className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700"
                                    >
                                        Add URL
                                    </button>
                                </div>
                            )}
                        </section>
                    )}

                    {/* Metadata */}
                    <section>
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                            Metadata
                        </h3>
                        {renderField('Created At', formatDate(displayEntity.created_at))}
                        {renderField('Updated At', formatDate(displayEntity.updated_at))}
                    </section>
                        </>
                    )}
                    
                    {/* Print-only: Show "Relations" heading and page break */}
                    <div className="hidden print:block page-break-before">
                        <h2 className="text-2xl font-bold text-gray-900 border-b-2 border-gray-300 pb-2 mb-4">Relations</h2>
                    </div>

                    {/* Relations View */}
                    {(viewMode === 'relations' || window.matchMedia('print').matches) && (
                        <>
                            {isLoadingRelations ? (
                                <div className="text-center py-8">
                                    <p className="text-gray-500 dark:text-gray-400">Loading relations...</p>
                                </div>
                            ) : (
                                <>
                                    {/* Add Relation Button - Only in Edit Mode */}
                                    {isEditing && (
                                        <div className="mb-6 print:hidden">
                                            <button
                                                onClick={() => setIsAddingRelation(true)}
                                                className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition text-sm font-medium"
                                            >
                                                + Add Relation
                                            </button>
                                        </div>
                                    )}

                                    {/* Add Relation Form - Only in Edit Mode */}
                                    {isEditing && isAddingRelation && (
                                        <div className="mb-6 p-4 bg-gray-50 dark:bg-gray-700 rounded-lg border border-gray-200 dark:border-gray-600 print:hidden">
                                            <h4 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                                                Add New Relation
                                            </h4>

                                            {/* Entity Search */}
                                            <div className="mb-4">
                                                <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                                    Search Entity
                                                </label>
                                                <input
                                                    type="text"
                                                    placeholder="Type to search..."
                                                    value={newRelation.targetEntityData ? (newRelation.targetEntityData.display || newRelation.targetEntityData.label) : entitySearchQuery}
                                                    onChange={(e) => searchEntities(e.target.value)}
                                                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                    disabled={!!newRelation.targetEntityData}
                                                />
                                                {entitySearchResults.length > 0 && !newRelation.targetEntityData && (
                                                    <div className="mt-2 max-h-48 overflow-y-auto border border-gray-300 dark:border-gray-600 rounded-lg">
                                                        {entitySearchResults.map((result) => (
                                                            <button
                                                                key={result.id}
                                                                onClick={() => {
                                                                    setNewRelation(prev => ({
                                                                        ...prev,
                                                                        targetEntity: result.id,
                                                                        targetEntityData: result
                                                                    }));
                                                                    setEntitySearchResults([]);
                                                                    setEntitySearchQuery('');
                                                                    // Update available relation types based on selected entity
                                                                    const validRelations = getValidRelationTypes(entity.type, result.type);
                                                                    setAvailableRelationTypes(validRelations);
                                                                }}
                                                                className="w-full text-left px-3 py-2 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                                                            >
                                                                <div className="font-medium text-gray-900 dark:text-gray-100">
                                                                    {result.display || result.label}
                                                                </div>
                                                                <div className="text-sm text-gray-500 dark:text-gray-400">
                                                                    {result.type}
                                                                </div>
                                                            </button>
                                                        ))}
                                                    </div>
                                                )}
                                                {newRelation.targetEntityData && (
                                                    <div className="mt-2 flex items-center justify-between">
                                                        <p className="text-sm text-green-600 dark:text-green-400">
                                                            {newRelation.targetEntityData.display || newRelation.targetEntityData.label} ({newRelation.targetEntityData.type}) selected ✓
                                                        </p>
                                                        <button
                                                            onClick={() => {
                                                                setNewRelation(prev => ({
                                                                    ...prev,
                                                                    targetEntity: '',
                                                                    targetEntityData: null,
                                                                    relationType: ''
                                                                }));
                                                                setEntitySearchQuery('');
                                                                fetchAvailableRelationTypes();
                                                            }}
                                                            className="text-sm text-red-600 dark:text-red-400 hover:underline"
                                                        >
                                                            Clear
                                                        </button>
                                                    </div>
                                                )}
                                            </div>

                                            {/* Relation Type */}
                                            <div className="mb-4">
                                                <label className="block text-sm font-semibold text-gray-600 dark:text-gray-400 mb-1">
                                                    Relation Type
                                                </label>
                                                <select
                                                    value={newRelation.relationType}
                                                    onChange={(e) => setNewRelation(prev => ({ ...prev, relationType: e.target.value }))}
                                                    className="w-full px-3 py-2 rounded-lg border border-gray-300 dark:border-gray-600 bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100"
                                                >
                                                    <option value="">Select relation type</option>
                                                    {availableRelationTypes.map((type) => (
                                                        <option key={type} value={type}>
                                                            {type.replace(/_/g, ' ')}
                                                        </option>
                                                    ))}
                                                </select>
                                            </div>

                                            {/* Action Buttons */}
                                            <div className="flex gap-2">
                                                <button
                                                    onClick={handleAddRelation}
                                                    className="px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition text-sm font-medium"
                                                >
                                                    Add
                                                </button>
                                                <button
                                                    onClick={() => {
                                                        setIsAddingRelation(false);
                                                        setNewRelation({ targetEntity: '', relationType: '', targetEntityData: null });
                                                        setEntitySearchResults([]);
                                                        setEntitySearchQuery('');
                                                    }}
                                                    className="px-4 py-2 bg-gray-300 dark:bg-gray-600 text-gray-900 dark:text-gray-100 rounded-lg hover:bg-gray-400 dark:hover:bg-gray-500 transition text-sm font-medium"
                                                >
                                                    Cancel
                                                </button>
                                            </div>
                                        </div>
                                    )}

                                    {/* Relations List - Grouped by Type */}
                                    <section>
                                        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-3 border-b border-gray-200 dark:border-gray-700 pb-2">
                                            Relations ({relations.outgoing.length})
                                        </h3>

                                        {/* Filter and Expand/Collapse Controls */}
                                        {relations.outgoing.length > 0 && (
                                            <div className="mb-4 space-y-2">
                                                <div className="flex gap-2">
                                                    <input
                                                        type="text"
                                                        placeholder="Filter entities by name..."
                                                        value={relationsFilter}
                                                        onChange={(e) => setRelationsFilter(e.target.value)}
                                                        className="flex-1 px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 placeholder-gray-500 dark:placeholder-gray-400 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                                    />
                                                    <button
                                                        onClick={() => {
                                                            const allTypes = Object.keys(relations.outgoing.reduce((groups, rel) => {
                                                                groups[rel.relation_type] = true;
                                                                return groups;
                                                            }, {}));
                                                            const expanded = {};
                                                            allTypes.forEach(type => expanded[type] = true);
                                                            setExpandedRelations(expanded);
                                                        }}
                                                        className="px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition whitespace-nowrap"
                                                        title="Expand all relation groups"
                                                    >
                                                        Expand All
                                                    </button>
                                                    <button
                                                        onClick={() => {
                                                            const allTypes = Object.keys(relations.outgoing.reduce((groups, rel) => {
                                                                groups[rel.relation_type] = true;
                                                                return groups;
                                                            }, {}));
                                                            const collapsed = {};
                                                            allTypes.forEach(type => collapsed[type] = false);
                                                            setExpandedRelations(collapsed);
                                                        }}
                                                        className="px-3 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-gray-100 dark:bg-gray-700 hover:bg-gray-200 dark:hover:bg-gray-600 rounded-lg transition whitespace-nowrap"
                                                        title="Collapse all relation groups"
                                                    >
                                                        Collapse All
                                                    </button>
                                                </div>
                                                {relationsFilter && (
                                                    <button
                                                        onClick={() => setRelationsFilter('')}
                                                        className="text-sm text-blue-600 dark:text-blue-400 hover:underline"
                                                    >
                                                        Clear filter
                                                    </button>
                                                )}
                                            </div>
                                        )}

                                        {relations.outgoing.length === 0 ? (
                                            <p className="text-gray-500 dark:text-gray-400 text-sm">No relations</p>
                                        ) : (
                                            <div className="space-y-4">
                                                {/* Group relations by type */}
                                                {Object.entries(
                                                    relations.outgoing.reduce((groups, rel) => {
                                                        const type = rel.relation_type;
                                                        if (!groups[type]) {
                                                            groups[type] = [];
                                                        }
                                                        groups[type].push(rel);
                                                        return groups;
                                                    }, {})
                                                ).map(([relationType, rels]) => {
                                                    // Filter entities based on search
                                                    const filteredRels = rels.filter((rel) => {
                                                        if (!relationsFilter) return true;
                                                        const entityName = (rel.entity.display || rel.entity.label || '').toLowerCase();
                                                        return entityName.includes(relationsFilter.toLowerCase());
                                                    });

                                                    // Don't show relation type if no entities match filter
                                                    if (filteredRels.length === 0) return null;

                                                    const isExpanded = expandedRelations[relationType] !== false;

                                                    return (
                                                        <div key={relationType} className="space-y-2">
                                                            {/* Relation Type Header */}
                                                            <div className="flex items-center gap-2">
                                                                <button
                                                                    onClick={() => {
                                                                        setExpandedRelations(prev => ({
                                                                            ...prev,
                                                                            [relationType]: !isExpanded
                                                                        }));
                                                                    }}
                                                                    className="p-1 hover:bg-gray-200 dark:hover:bg-gray-600 rounded transition"
                                                                    title={isExpanded ? "Collapse" : "Expand"}
                                                                >
                                                                    <svg
                                                                        className={`w-4 h-4 text-gray-600 dark:text-gray-400 transition-transform ${isExpanded ? 'rotate-90' : ''}`}
                                                                        fill="none"
                                                                        stroke="currentColor"
                                                                        viewBox="0 0 24 24"
                                                                    >
                                                                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                                                    </svg>
                                                                </button>
                                                                <span className="px-2 py-1 text-xs font-semibold bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded">
                                                                    {relationType.replace(/_/g, ' ')}
                                                                </span>
                                                                <span className="text-sm text-gray-500 dark:text-gray-400">
                                                                    ({filteredRels.length}{relationsFilter && ` of ${rels.length}`})
                                                                </span>
                                                            </div>

                                                            {/* Entities with this relation type */}
                                                            {isExpanded && (
                                                                <div className="ml-4 space-y-2">
                                                                {filteredRels
                                                                    .sort((a, b) => {
                                                                        const aName = (a.entity.display || a.entity.label || '').toLowerCase();
                                                                        const bName = (b.entity.display || b.entity.label || '').toLowerCase();
                                                                        return aName.localeCompare(bName);
                                                                    })
                                                                    .map((rel) => (
                                                                <div
                                                                    key={rel.id}
                                                                    className="flex items-center justify-between p-2 bg-gray-50 dark:bg-gray-700 rounded-lg"
                                                                >
                                                                    <div className="flex-1 min-w-0">
                                                                        <button
                                                                            onClick={async () => {
                                                                                // Fetch the full entity data
                                                                                try {
                                                                                    const response = await api.fetch(`/api/entities/${rel.entity.id}/`);
                                                                                    if (response.ok) {
                                                                                        const entityData = await response.json();
                                                                                        // Load the entity into the detail panel with relations tab active
                                                                                        if (onUpdate) {
                                                                                            onUpdate({ ...entityData, _navigate: true, _viewMode: 'relations' });
                                                                                        }
                                                                                    }
                                                                                } catch (error) {
                                                                                    console.error('Failed to load related entity:', error);
                                                                                }
                                                                            }}
                                                                            className="text-gray-900 dark:text-gray-100 font-medium hover:text-blue-600 dark:hover:text-blue-400 hover:underline transition text-left"
                                                                            title={`View ${rel.entity.display || rel.entity.label}`}
                                                                        >
                                                                        {rel.entity.display || rel.entity.label}
                                                                    </button>
                                                                </div>
                                                                    {/* Delete Button - Only in Edit Mode */}
                                                                    {isEditing && (
                                                                        <button
                                                                            onClick={() => handleDeleteRelation(rel.id)}
                                                                            className="p-2 text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900 rounded transition flex-shrink-0"
                                                                            title="Delete relation"
                                                                        >
                                                                            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                                                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                                                            </svg>
                                                                        </button>
                                                                    )}
                                                                </div>
                                                                    ))}
                                                                </div>
                                                            )}
                                                        </div>
                                                    );
                                                })}
                                            </div>
                                        )}
                                    </section>
                                </>
                            )}
                        </>
                    )}
                    </>
                    )}
                </div>
            </div>

            {/* Image Lightbox */}
            <ImageLightbox
                images={lightboxImages}
                currentIndex={lightboxIndex}
                onClose={() => {
                    lightboxImages.forEach(url => {
                        if (url.startsWith('blob:')) {
                            URL.revokeObjectURL(url);
                        }
                    });
                    setLightboxImages([]);
                    setLightboxIndex(0);
                }}
                onNavigate={setLightboxIndex}
            />
        </>
    );
}

export default EntityDetail;