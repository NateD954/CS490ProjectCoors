import { SignedIn, SignedOut, RedirectToSignIn } from '@clerk/clerk-react'
import { Routes, Route, Navigate } from 'react-router-dom'
import SignInPage from './pages/SignInPage'
import Home from './pages/Home'

export default function App() {
    return (
        <Routes>
            <Route path="/sign-in/*" element={<SignInPage />} />
            <Route
                path="/"
                element={
                    <>
                        <SignedIn>
                            <Home />
                        </SignedIn>
                        <SignedOut>
                            <RedirectToSignIn />
                        </SignedOut>
                    </>
                }
            />
        </Routes>
    )
}
