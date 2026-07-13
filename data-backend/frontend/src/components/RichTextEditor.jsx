import { getMediaUrl } from '../utils/apiUrl';
import React, { useState } from 'react';
import api from '../services/api';
import { useEditor, EditorContent } from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import Placeholder from '@tiptap/extension-placeholder';
import Image from '@tiptap/extension-image';
import TextAlign from '@tiptap/extension-text-align';
import Youtube from '@tiptap/extension-youtube';
import { Table } from '@tiptap/extension-table';
import { TableRow } from '@tiptap/extension-table-row';
import { TableCell } from '@tiptap/extension-table-cell';
import { TableHeader } from '@tiptap/extension-table-header';
import TurndownService from 'turndown';
import { marked } from 'marked';
import './RichTextEditor.css';

// Custom Image extension with resize support
const ResizableImage = Image.extend({
    addAttributes() {
        return {
            ...this.parent?.(),
            width: {
                default: null,
                renderHTML: attributes => {
                    if (!attributes.width) {
                        return {};
                    }
                    return {
                        width: attributes.width,
                    };
                },
            },
            height: {
                default: null,
                renderHTML: attributes => {
                    if (!attributes.height) {
                        return {};
                    }
                    return {
                        height: attributes.height,
                    };
                },
            },
        };
    },
});

function RichTextEditor({ value, onChange, placeholder = 'Enter description...' }) {
    const [showImageDialog, setShowImageDialog] = useState(false);
    const [showYoutubeDialog, setShowYoutubeDialog] = useState(false);
    const [imageUrl, setImageUrl] = useState('');
    const [youtubeUrl, setYoutubeUrl] = useState('');
    const [isUploading, setIsUploading] = useState(false);
    const [uploadError, setUploadError] = useState('');
    const [isImageSelected, setIsImageSelected] = useState(false);
    const [editMode, setEditMode] = useState('wysiwyg'); // 'wysiwyg', 'html', 'markdown'
    const [rawContent, setRawContent] = useState('');

    const editor = useEditor({
        extensions: [
            StarterKit,
            Placeholder.configure({
                placeholder,
            }),
            TextAlign.configure({
                types: ['heading', 'paragraph', 'image'],
                alignments: ['left', 'center', 'right', 'justify'],
            }),
            ResizableImage.configure({
                inline: true,
                allowBase64: true,
                HTMLAttributes: {
                    class: 'tiptap-image',
                },
            }),
            Youtube.configure({
                controls: true,
                nocookie: true,
                modestBranding: true,
                HTMLAttributes: {
                    class: 'tiptap-youtube',
                },
            }),
            Table.configure({
                resizable: true,
            }),
            TableRow,
            TableHeader,
            TableCell,
        ],
        content: value || '',
        onUpdate: ({ editor }) => {
            const html = editor.getHTML();
            onChange(html);
        },
        onSelectionUpdate: ({ editor }) => {
            // Check if an image node is selected
            const { node } = editor.state.selection;
            setIsImageSelected(node && node.type.name === 'image');
        },
    });

    // Update editor content when value changes externally
    React.useEffect(() => {
        if (editor && value !== editor.getHTML()) {
            editor.commands.setContent(value || '');
        }
    }, [value, editor]);

    const addImage = () => {
        if (imageUrl) {
            editor.chain().focus().setImage({ src: imageUrl }).run();
            setImageUrl('');
            setShowImageDialog(false);
            setUploadError('');
        }
    };

    const handleImageUpload = async (e) => {
        const file = e.target.files?.[0];
        if (!file) return;

        // Check if it's an image
        if (!file.type.startsWith('image/')) {
            setUploadError('Please select an image file');
            return;
        }

        setIsUploading(true);
        setUploadError('');

        try {
            const formData = new FormData();
            formData.append('file', file);

            const response = await api.fetch('/api/upload/', {
                method: 'POST',
                body: formData,
            });

            if (response.ok) {
                const result = await response.json();
                // Use the full URL from the upload result
		const uploadedUrl = getMediaUrl(result.url);
                
                editor.chain().focus().setImage({ src: uploadedUrl }).run();
                setShowImageDialog(false);
                setImageUrl('');
            } else {
                const error = await response.json();
                setUploadError(`Upload failed: ${JSON.stringify(error)}`);
            }
        } catch (error) {
            console.error('Error uploading image:', error);
            setUploadError('Error uploading image');
        } finally {
            setIsUploading(false);
        }
    };

    const addTable = () => {
        editor.chain().focus().insertTable({ rows: 3, cols: 3, withHeaderRow: true }).run();
    };

    const addYoutube = () => {
        if (youtubeUrl) {
            editor.chain().focus().setYoutubeVideo({ src: youtubeUrl }).run();
            setYoutubeUrl('');
            setShowYoutubeDialog(false);
        }
    };

    const handleModeChange = (newMode) => {
        if (newMode === editMode) return;

        if (editMode === 'wysiwyg') {
            // Switching from WYSIWYG to HTML/Markdown
            const html = editor.getHTML();
            if (newMode === 'html') {
                setRawContent(html);
            } else if (newMode === 'markdown') {
                const turndownService = new TurndownService({
                    headingStyle: 'atx',
                    codeBlockStyle: 'fenced',
                });
                const markdown = turndownService.turndown(html);
                setRawContent(markdown);
            }
        } else if (newMode === 'wysiwyg') {
            // Switching from HTML/Markdown to WYSIWYG
            let html = rawContent;
            if (editMode === 'markdown') {
                html = marked.parse(rawContent);
            }
            editor.commands.setContent(html);
            onChange(html);
        } else {
            // Switching between HTML and Markdown
            if (editMode === 'html' && newMode === 'markdown') {
                const turndownService = new TurndownService({
                    headingStyle: 'atx',
                    codeBlockStyle: 'fenced',
                });
                const markdown = turndownService.turndown(rawContent);
                setRawContent(markdown);
            } else if (editMode === 'markdown' && newMode === 'html') {
                const html = marked.parse(rawContent);
                setRawContent(html);
            }
        }

        setEditMode(newMode);
    };

    const handleRawContentChange = (e) => {
        const newContent = e.target.value;
        setRawContent(newContent);
        
        // Update editor content in real-time for preview
        let html = newContent;
        if (editMode === 'markdown') {
            html = marked.parse(newContent);
        }
        onChange(html);
    };

    if (!editor) {
        return null;
    }

    return (
        <div className="border border-gray-300 dark:border-gray-600 rounded-lg overflow-hidden bg-white dark:bg-gray-800">
            {/* Mode Toggle */}
            <div className="border-b border-gray-300 dark:border-gray-600 bg-gray-100 dark:bg-gray-750 px-2 py-1 flex gap-1">
                <button
                    onClick={() => handleModeChange('wysiwyg')}
                    className={`px-3 py-1 rounded text-xs font-medium transition ${
                        editMode === 'wysiwyg'
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                >
                    WYSIWYG
                </button>
                <button
                    onClick={() => handleModeChange('html')}
                    className={`px-3 py-1 rounded text-xs font-medium transition ${
                        editMode === 'html'
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                >
                    HTML
                </button>
                <button
                    onClick={() => handleModeChange('markdown')}
                    className={`px-3 py-1 rounded text-xs font-medium transition ${
                        editMode === 'markdown'
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-200 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                >
                    Markdown
                </button>
            </div>
            
            {/* Toolbar - only show in WYSIWYG mode */}
            {editMode === 'wysiwyg' && (
            <div className="border-b border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-700 p-2 flex flex-wrap gap-1">
                <button
                    onClick={() => editor.chain().focus().toggleBold().run()}
                    className={`px-3 py-1 rounded text-sm font-bold transition ${
                        editor.isActive('bold')
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Bold"
                >
                    B
                </button>
                <button
                    onClick={() => editor.chain().focus().toggleItalic().run()}
                    className={`px-3 py-1 rounded text-sm italic transition ${
                        editor.isActive('italic')
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Italic"
                >
                    I
                </button>
                <button
                    onClick={() => editor.chain().focus().toggleStrike().run()}
                    className={`px-3 py-1 rounded text-sm line-through transition ${
                        editor.isActive('strike')
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Strikethrough"
                >
                    S
                </button>
                
                <div className="w-px bg-gray-300 dark:bg-gray-600 mx-1" />
                
                <button
                    onClick={() => editor.chain().focus().toggleHeading({ level: 1 }).run()}
                    className={`px-3 py-1 rounded text-sm font-bold transition ${
                        editor.isActive('heading', { level: 1 })
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Heading 1"
                >
                    H1
                </button>
                <button
                    onClick={() => editor.chain().focus().toggleHeading({ level: 2 }).run()}
                    className={`px-3 py-1 rounded text-sm font-bold transition ${
                        editor.isActive('heading', { level: 2 })
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Heading 2"
                >
                    H2
                </button>
                <button
                    onClick={() => editor.chain().focus().toggleHeading({ level: 3 }).run()}
                    className={`px-3 py-1 rounded text-sm font-bold transition ${
                        editor.isActive('heading', { level: 3 })
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Heading 3"
                >
                    H3
                </button>
                
                <div className="w-px bg-gray-300 dark:bg-gray-600 mx-1" />
                
                <button
                    onClick={() => editor.chain().focus().toggleBulletList().run()}
                    className={`px-3 py-1 rounded text-sm transition ${
                        editor.isActive('bulletList')
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Bullet List"
                >
                    •
                </button>
                <button
                    onClick={() => editor.chain().focus().toggleOrderedList().run()}
                    className={`px-3 py-1 rounded text-sm transition ${
                        editor.isActive('orderedList')
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Numbered List"
                >
                    1.
                </button>
                
                <div className="w-px bg-gray-300 dark:bg-gray-600 mx-1" />
                
                <button
                    onClick={() => editor.chain().focus().toggleBlockquote().run()}
                    className={`px-3 py-1 rounded text-sm transition ${
                        editor.isActive('blockquote')
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Quote"
                >
                    "
                </button>
                <button
                    onClick={() => editor.chain().focus().toggleCodeBlock().run()}
                    className={`px-3 py-1 rounded text-sm font-mono transition ${
                        editor.isActive('codeBlock')
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Code Block"
                >
                    &lt;/&gt;
                </button>
                
                <div className="w-px bg-gray-300 dark:bg-gray-600 mx-1" />
                
                <button
                    onClick={() => editor.chain().focus().setHorizontalRule().run()}
                    className="px-3 py-1 rounded text-sm bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                    type="button"
                    title="Horizontal Rule"
                >
                    ―
                </button>
                
                <div className="w-px bg-gray-300 dark:bg-gray-600 mx-1" />
                
                {/* Alignment Buttons */}
                <button
                    onClick={() => editor.chain().focus().setTextAlign('left').run()}
                    className={`px-2 py-1 rounded text-sm transition ${
                        editor.isActive({ textAlign: 'left' })
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Align Left"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h10M4 18h16" />
                    </svg>
                </button>
                <button
                    onClick={() => editor.chain().focus().setTextAlign('center').run()}
                    className={`px-2 py-1 rounded text-sm transition ${
                        editor.isActive({ textAlign: 'center' })
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Align Center"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M7 12h10M4 18h16" />
                    </svg>
                </button>
                <button
                    onClick={() => editor.chain().focus().setTextAlign('right').run()}
                    className={`px-2 py-1 rounded text-sm transition ${
                        editor.isActive({ textAlign: 'right' })
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Align Right"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M10 12h10M4 18h16" />
                    </svg>
                </button>
                <button
                    onClick={() => editor.chain().focus().setTextAlign('justify').run()}
                    className={`px-2 py-1 rounded text-sm transition ${
                        editor.isActive({ textAlign: 'justify' })
                            ? 'bg-blue-600 text-white'
                            : 'bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600'
                    }`}
                    type="button"
                    title="Justify"
                >
                    <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                    </svg>
                </button>
                
                <div className="w-px bg-gray-300 dark:bg-gray-600 mx-1" />
                
                <button
                    onClick={() => setShowImageDialog(true)}
                    className="px-3 py-1 rounded text-sm bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                    type="button"
                    title="Insert Image"
                >
                    🖼️
                </button>
                <button
                    onClick={() => setShowYoutubeDialog(true)}
                    className="px-3 py-1 rounded text-sm bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                    type="button"
                    title="Insert YouTube Video"
                >
                    ▶️
                </button>
                <button
                    onClick={addTable}
                    className="px-3 py-1 rounded text-sm bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                    type="button"
                    title="Insert Table"
                >
                    ⊞
                </button>
                
                {/* Table editing buttons - only show when inside a table */}
                {editor.isActive('table') && (
                    <>
                        <div className="w-px bg-gray-300 dark:bg-gray-600 mx-1" />
                        <button
                            onClick={() => editor.chain().focus().addColumnBefore().run()}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Add Column Before"
                        >
                            ⊞←
                        </button>
                        <button
                            onClick={() => editor.chain().focus().addColumnAfter().run()}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Add Column After"
                        >
                            ⊞→
                        </button>
                        <button
                            onClick={() => editor.chain().focus().deleteColumn().run()}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Delete Column"
                        >
                            ⊟↕
                        </button>
                        <button
                            onClick={() => editor.chain().focus().addRowBefore().run()}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Add Row Before"
                        >
                            ⊞↑
                        </button>
                        <button
                            onClick={() => editor.chain().focus().addRowAfter().run()}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Add Row After"
                        >
                            ⊞↓
                        </button>
                        <button
                            onClick={() => editor.chain().focus().deleteRow().run()}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Delete Row"
                        >
                            ⊟↔
                        </button>
                        <button
                            onClick={() => editor.chain().focus().deleteTable().run()}
                            className="px-2 py-1 rounded text-xs bg-red-100 dark:bg-red-900 text-red-700 dark:text-red-300 hover:bg-red-200 dark:hover:bg-red-800 transition"
                            type="button"
                            title="Delete Table"
                        >
                            ✕
                        </button>
                    </>
                )}

                {/* Image-specific controls - only show when an image is selected */}
                {isImageSelected && (
                    <>
                        <div className="w-px bg-gray-300 dark:bg-gray-600 mx-1" />
                        <span className="text-xs text-gray-600 dark:text-gray-400 px-2">Image Size:</span>
                        <button
                            onClick={() => {
                                editor.chain().focus().updateAttributes('image', { width: '25%', height: null }).run();
                            }}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Small (25%)"
                        >
                            Small
                        </button>
                        <button
                            onClick={() => {
                                editor.chain().focus().updateAttributes('image', { width: '50%', height: null }).run();
                            }}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Medium (50%)"
                        >
                            Medium
                        </button>
                        <button
                            onClick={() => {
                                editor.chain().focus().updateAttributes('image', { width: '75%', height: null }).run();
                            }}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Large (75%)"
                        >
                            Large
                        </button>
                        <button
                            onClick={() => {
                                editor.chain().focus().updateAttributes('image', { width: '100%', height: null }).run();
                            }}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Full Width (100%)"
                        >
                            Full
                        </button>
                        <button
                            onClick={() => {
                                editor.chain().focus().updateAttributes('image', { width: null, height: null }).run();
                            }}
                            className="px-2 py-1 rounded text-xs bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition"
                            type="button"
                            title="Original Size"
                        >
                            Original
                        </button>
                    </>
                )}
                
                <div className="w-px bg-gray-300 dark:bg-gray-600 mx-1" />
                
                <button
                    onClick={() => editor.chain().focus().undo().run()}
                    disabled={!editor.can().undo()}
                    className="px-3 py-1 rounded text-sm bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition disabled:opacity-30 disabled:cursor-not-allowed"
                    type="button"
                    title="Undo"
                >
                    ↶
                </button>
                <button
                    onClick={() => editor.chain().focus().redo().run()}
                    disabled={!editor.can().redo()}
                    className="px-3 py-1 rounded text-sm bg-white dark:bg-gray-800 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-600 transition disabled:opacity-30 disabled:cursor-not-allowed"
                    type="button"
                    title="Redo"
                >
                    ↷
                </button>
            </div>
            )}
            
            {/* Editor Content - WYSIWYG mode */}
            {editMode === 'wysiwyg' && (
                <EditorContent 
                    editor={editor} 
                    className="prose dark:prose-invert max-w-none p-4 min-h-[200px] focus:outline-none"
                />
            )}
            
            {/* Raw Content Editor - HTML/Markdown mode */}
            {(editMode === 'html' || editMode === 'markdown') && (
                <textarea
                    value={rawContent}
                    onChange={handleRawContentChange}
                    placeholder={editMode === 'html' ? 'Paste or type HTML...' : 'Paste or type Markdown...'}
                    className="w-full p-4 min-h-[200px] font-mono text-sm bg-white dark:bg-gray-800 text-gray-900 dark:text-gray-100 focus:outline-none resize-y"
                    spellCheck="false"
                />
            )}
            
            {/* Image Dialog */}
            {showImageDialog && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                            Insert Image
                        </h3>
                        
                        {/* Upload Section */}
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Upload Image
                            </label>
                            <div className="flex items-center gap-2">
                                <label className="flex-1 cursor-pointer">
                                    <div className="px-4 py-2 border-2 border-dashed border-gray-300 dark:border-gray-600 rounded-lg hover:border-blue-500 dark:hover:border-blue-400 transition text-center">
                                        <svg className="w-8 h-8 mx-auto mb-2 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M7 16a4 4 0 01-.88-7.903A5 5 0 1115.9 6L16 6a5 5 0 011 9.9M15 13l-3-3m0 0l-3 3m3-3v12" />
                                        </svg>
                                        <span className="text-sm text-gray-600 dark:text-gray-400">
                                            {isUploading ? 'Uploading...' : 'Click to upload'}
                                        </span>
                                    </div>
                                    <input
                                        type="file"
                                        accept="image/*"
                                        onChange={handleImageUpload}
                                        disabled={isUploading}
                                        className="hidden"
                                    />
                                </label>
                            </div>
                            {uploadError && (
                                <p className="mt-2 text-sm text-red-600 dark:text-red-400">
                                    {uploadError}
                                </p>
                            )}
                        </div>
                        
                        {/* Divider */}
                        <div className="relative mb-4">
                            <div className="absolute inset-0 flex items-center">
                                <div className="w-full border-t border-gray-300 dark:border-gray-600"></div>
                            </div>
                            <div className="relative flex justify-center text-sm">
                                <span className="px-2 bg-white dark:bg-gray-800 text-gray-500 dark:text-gray-400">
                                    OR
                                </span>
                            </div>
                        </div>
                        
                        {/* URL Section */}
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                Image URL
                            </label>
                            <input
                                type="text"
                                value={imageUrl}
                                onChange={(e) => {
                                    setImageUrl(e.target.value);
                                    setUploadError('');
                                }}
                                placeholder="https://example.com/image.jpg"
                                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && imageUrl) {
                                        addImage();
                                    } else if (e.key === 'Escape') {
                                        setShowImageDialog(false);
                                        setImageUrl('');
                                        setUploadError('');
                                    }
                                }}
                                disabled={isUploading}
                            />
                        </div>
                        
                        {/* Action Buttons */}
                        <div className="flex gap-2 justify-end">
                            <button
                                onClick={() => {
                                    setShowImageDialog(false);
                                    setImageUrl('');
                                    setUploadError('');
                                }}
                                disabled={isUploading}
                                className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition disabled:opacity-50"
                                type="button"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={addImage}
                                disabled={!imageUrl || isUploading}
                                className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
                                type="button"
                            >
                                Insert URL
                            </button>
                        </div>
                    </div>
                </div>
            )}
            
            {/* YouTube Dialog */}
            {showYoutubeDialog && (
                <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50">
                    <div className="bg-white dark:bg-gray-800 rounded-lg p-6 max-w-md w-full mx-4">
                        <h3 className="text-lg font-semibold text-gray-900 dark:text-gray-100 mb-4">
                            Insert YouTube Video
                        </h3>
                        
                        <div className="mb-4">
                            <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-2">
                                YouTube URL
                            </label>
                            <input
                                type="text"
                                value={youtubeUrl}
                                onChange={(e) => setYoutubeUrl(e.target.value)}
                                placeholder="https://www.youtube.com/watch?v=..."
                                className="w-full px-3 py-2 border border-gray-300 dark:border-gray-600 rounded-lg bg-white dark:bg-gray-700 text-gray-900 dark:text-gray-100 focus:ring-2 focus:ring-blue-500 focus:border-transparent"
                                onKeyDown={(e) => {
                                    if (e.key === 'Enter' && youtubeUrl) {
                                        addYoutube();
                                    } else if (e.key === 'Escape') {
                                        setShowYoutubeDialog(false);
                                        setYoutubeUrl('');
                                    }
                                }}
                            />
                            <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                                Paste any YouTube URL (watch, embed, or short link)
                            </p>
                        </div>
                        
                        <div className="flex gap-2 justify-end">
                            <button
                                onClick={() => {
                                    setShowYoutubeDialog(false);
                                    setYoutubeUrl('');
                                }}
                                className="px-4 py-2 rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-300 hover:bg-gray-100 dark:hover:bg-gray-700 transition"
                                type="button"
                            >
                                Cancel
                            </button>
                            <button
                                onClick={addYoutube}
                                disabled={!youtubeUrl}
                                className="px-4 py-2 rounded-lg bg-blue-600 text-white hover:bg-blue-700 transition disabled:opacity-50 disabled:cursor-not-allowed"
                                type="button"
                            >
                                Insert
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    );
}

export default RichTextEditor;
