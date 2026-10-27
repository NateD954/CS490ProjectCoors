import { SignIn } from '@clerk/clerk-react'

export default function SignInPage() {
    return (
        <div style={{ display: 'flex', justifyContent: 'center', marginTop: '100px' }}>
            <SignIn redirectUrl="/" />
        </div>
    )
}
